#!/usr/bin/env python3
# Copyright (c) 2026-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test that read-only block file operations handle missing directories gracefully.

FlatFileSeq::Open (flatfile.cpp) calls fs::create_directories() even when opening
files for reading. If the blocks directory becomes inaccessible (e.g. NFS disconnect,
volume detach), this throws an unhandled filesystem_error that either crashes the
node or silently freezes chain progress depending on where it occurs.

The fix skips directory creation for read-only opens, letting fopen() fail naturally
and return NULL -- which all callers already handle.
"""

import contextlib
import os
import re
import stat

from test_framework.blocktools import (
    add_witness_commitment,
    create_block,
    create_coinbase,
)
from test_framework.messages import (
    BlockTransactionsRequest,
    CInv,
    MSG_BLOCK,
    MSG_WITNESS_FLAG,
    msg_block,
    msg_getblocktxn,
    msg_getdata,
)
from test_framework.p2p import P2PInterface
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal

COINBASE_MATURITY = 100


@contextlib.contextmanager
def simulate_nfs_disconnect(blocks_path):
    """Make the blocks directory inaccessible by renaming it.

    Open LevelDB file descriptors survive the rename (POSIX inode semantics),
    so the node keeps running -- only new file opens fail.
    """
    blocks_bak = blocks_path.parent / "blocks_bak"
    parent_dir = blocks_path.parent
    old_mode = stat.S_IMODE(os.stat(parent_dir).st_mode)

    os.rename(blocks_path, blocks_bak)
    os.chmod(parent_dir, 0o500)  # Prevent re-creation of blocks/
    try:
        yield
    finally:
        os.chmod(parent_dir, old_mode)
        if blocks_bak.exists() and not blocks_path.exists():
            os.rename(blocks_bak, blocks_path)


def make_block(hashprev, height, time):
    block = create_block(hashprev, create_coinbase(height), time)
    add_witness_commitment(block)
    block.solve()
    return block


class SilentStuckNodeTest(BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 1
        self.setup_clean_chain = True

    def test_reorg_on_broken_fs(self):
        """A P2P block that triggers a reorg while the blocks directory is
        inaccessible should cause a clean FatalError shutdown.

        We set up two competing chains (A and B) from the same parent, put
        the node on the shorter A-chain, break the filesystem, then send the
        longer B-chain tip via P2P. The node tries to disconnect A but cannot
        read the block from disk.

        Chain layout:
                          A    <-- active tip (shorter)
                         /
            genesis ... N
                         \\
                          B1 - B2  <-- stored, more work, not active

        With fix: ReadBlock returns false, DisconnectTip returns false, and
        FatalError shuts down the node cleanly.

        Without fix: fs::create_directories throws, the exception bypasses
        FatalError entirely and is caught by ProcessMessage's catch-all with
        a DEBUG-only log. The block is never marked invalid, so every future
        P2P block retries the same failing reorg -- the node looks healthy
        but the chain is frozen forever.
        """
        self.log.info("Test reorg on broken filesystem")
        node = self.nodes[0]

        self.generate(node, COINBASE_MATURITY + 10, sync_fun=self.no_op)
        tip = int(node.getbestblockhash(), 16)
        height = node.getblockcount()
        tip_time = node.getblock(node.getbestblockhash())['time']

        block_a = make_block(tip, height + 1, tip_time + 1)
        block_b1 = make_block(tip, height + 1, tip_time + 2)
        block_b2 = make_block(block_b1.hash_int, height + 2, tip_time + 3)

        # Deliver both branches via P2P. B-chain has more work so the node
        # reorgs from A to B.
        peer = node.add_p2p_connection(P2PInterface())
        peer.send_and_ping(msg_block(block_a))
        peer.send_and_ping(msg_block(block_b1))
        peer.send_and_ping(msg_block(block_b2))
        assert_equal(node.getblockcount(), height + 2)
        node.disconnect_p2ps()

        # Put the node back on the shorter A-chain.
        node.invalidateblock(block_b1.hash_hex)
        assert_equal(node.getbestblockhash(), block_a.hash_hex)

        with simulate_nfs_disconnect(node.blocks_path):
            # Clear the invalid flag so the node will want to reorg back to B.
            # reconsiderblock also calls ActivateBestChain internally, which
            # will fail -- we just catch the RPC error and move on.
            try:
                node.reconsiderblock(block_b1.hash_hex)
            except Exception:
                pass

            # If the node is still running (no fix), demonstrate the stuck
            # behavior: send B2 via P2P, watch it get silently swallowed.
            if node.process.poll() is None:
                peer = node.add_p2p_connection(P2PInterface())
                with node.assert_debug_log(["Exception 'filesystem error"], timeout=10):
                    peer.send_without_ping(msg_block(block_b2))
                # Chain did not advance -- the node is stuck.
                assert_equal(node.getbestblockhash(), block_a.hash_hex)
                self.log.info("  Block silently swallowed, chain frozen (bug)")

            # With the fix the node shuts down via FatalError. Without the
            # fix it stays alive indefinitely and this times out.
            node.wait_until_stopped(
                expect_error=True,
                expected_stderr=re.compile(r"fatal internal error"),
                timeout=10,
            )

        self.log.info("  Node exited cleanly via FatalError")
        self.start_node(0)
        self.generate(node, 1, sync_fun=self.no_op)
        self.log.info("  Restarted successfully")

    def test_forward_connect_on_broken_fs(self):
        """Reconnecting a previously invalidated block on a broken filesystem
        should cause a FatalError, not a silent failure.

        This tests the ConnectTip path (validation.cpp:3016) rather than the
        DisconnectTip path tested above -- no reorg is involved, just reading
        a block to connect it forward.
        """
        self.log.info("Test forward-connect on broken filesystem")
        node = self.nodes[0]

        self.generate(node, 1, sync_fun=self.no_op)
        tip_hash = node.getbestblockhash()
        node.invalidateblock(tip_hash)

        with simulate_nfs_disconnect(node.blocks_path):
            with node.assert_debug_log(["Failed to read block"], timeout=10):
                try:
                    node.reconsiderblock(tip_hash)
                except Exception:
                    pass

            node.wait_until_stopped(
                expect_error=True,
                expected_stderr=re.compile(r"fatal internal error"),
                timeout=10,
            )

        self.log.info("  Node exited cleanly via FatalError")
        self.start_node(0)
        self.generate(node, 1, sync_fun=self.no_op)
        self.log.info("  Restarted successfully")

    def test_getdata_on_broken_fs(self):
        """A P2P GETDATA for a block that is not in the recent-block cache
        should disconnect the peer gracefully, not crash the node.

        ProcessGetData runs BEFORE ProcessMessage's try-catch
        (net_processing.cpp:5217 vs 5260), so without the fix the
        fs::create_directories exception propagates unhandled and kills
        the process.
        """
        self.log.info("Test GETDATA on broken filesystem")
        node = self.nodes[0]

        self.generate(node, 10, sync_fun=self.no_op)
        old_hash_int = int(node.getblockhash(3), 16)  # Not in recent cache

        peer = node.add_p2p_connection(P2PInterface())

        with simulate_nfs_disconnect(node.blocks_path):
            with node.assert_debug_log(["Cannot load block from disk"], timeout=10):
                peer.send_without_ping(msg_getdata([CInv(MSG_BLOCK | MSG_WITNESS_FLAG, old_hash_int)]))
                peer.wait_for_disconnect(timeout=10)

            # Node must still be running -- on master it would have crashed.
            node.getblockcount()

        self.log.info("  Peer disconnected, node alive")

    def test_getblocktxn_cache_miss(self):
        """A GETBLOCKTXN for a block not in the recent-block cache should
        be handled gracefully on a broken filesystem.

        This is a DIFFERENT code path from GETDATA: the GETBLOCKTXN handler
        (net_processing.cpp:4362) calls ReadBlock directly and then uses
        assert(ret) at line 4365. This test requires two fixes:

          1. The read-only guard in FlatFileSeq::Open
          2. Replacing assert(ret) with graceful error handling

        Without either fix: fs::create_directories throws inside
        ProcessMessage's catch-all, the request is silently dropped.
        With fix 1 only: fopen fails but assert(ret) aborts the process.
        With both fixes: error logged, peer disconnected, node alive.
        """
        self.log.info("Test GETBLOCKTXN cache miss on broken filesystem")
        node = self.nodes[0]

        # Generate two blocks so that the first one is evicted from the
        # m_most_recent_block cache.
        self.generate(node, 1, sync_fun=self.no_op)
        block_a_hash = int(node.getbestblockhash(), 16)
        self.generate(node, 1, sync_fun=self.no_op)

        peer = node.add_p2p_connection(P2PInterface())

        with simulate_nfs_disconnect(node.blocks_path):
            gbtn = msg_getblocktxn()
            gbtn.block_txn_request = BlockTransactionsRequest(blockhash=block_a_hash, indexes=[0])

            # "Unable to open file" proves the read-only guard is working:
            # fopen was reached instead of fs::create_directories throwing.
            with node.assert_debug_log(["Unable to open file"], timeout=10):
                peer.send_without_ping(gbtn)
                peer.wait_for_disconnect(timeout=10)

            # If the assert(ret) fix is also applied, the node is still alive.
            node.getblockcount()

        self.log.info("  Cache miss handled gracefully, node alive")

    def run_test(self):
        self.test_reorg_on_broken_fs()
        self.test_forward_connect_on_broken_fs()
        self.test_getdata_on_broken_fs()
        self.test_getblocktxn_cache_miss()


if __name__ == '__main__':
    SilentStuckNodeTest(__file__).main()
