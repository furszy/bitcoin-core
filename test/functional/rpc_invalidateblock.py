#!/usr/bin/env python3
# Copyright (c) 2014-2022 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test the invalidateblock RPC."""

from test_framework.test_framework import BitcoinTestFramework
from test_framework.address import ADDRESS_BCRT1_UNSPENDABLE_DESCRIPTOR
from test_framework.messages import (
    CBlockHeader,
    from_hex,
    msg_headers,
)
from test_framework.p2p import (
    P2PInterface
)
from test_framework.util import (
    assert_equal,
    assert_raises_rpc_error,
    try_rpc
)


class InvalidateTest(BitcoinTestFramework):
    def set_test_params(self):
        self.setup_clean_chain = True
        self.num_nodes = 3

    def setup_network(self):
        self.setup_nodes()

    def run_test(self):
        self.log.info("Make sure we repopulate setBlockIndexCandidates after InvalidateBlock:")
        self.log.info("Mine 4 blocks on Node 0")
        self.generate(self.nodes[0], 4, sync_fun=self.no_op)
        assert_equal(self.nodes[0].getblockcount(), 4)
        besthash_n0 = self.nodes[0].getbestblockhash()

        self.log.info("Mine competing 6 blocks on Node 1")
        self.generate(self.nodes[1], 6, sync_fun=self.no_op)
        assert_equal(self.nodes[1].getblockcount(), 6)

        self.log.info("Connect nodes to force a reorg")
        self.connect_nodes(0, 1)
        self.sync_blocks(self.nodes[0:2])
        assert_equal(self.nodes[0].getblockcount(), 6)
        badhash = self.nodes[1].getblockhash(2)

        self.log.info("Invalidate block 2 on node 0 and verify we reorg to node 0's original chain")
        self.nodes[0].invalidateblock(badhash)
        assert_equal(self.nodes[0].getblockcount(), 4)
        assert_equal(self.nodes[0].getbestblockhash(), besthash_n0)

        self.log.info("Make sure we won't reorg to a lower work chain:")
        self.connect_nodes(1, 2)
        self.log.info("Sync node 2 to node 1 so both have 6 blocks")
        self.sync_blocks(self.nodes[1:3])
        assert_equal(self.nodes[2].getblockcount(), 6)
        self.log.info("Invalidate block 5 on node 1 so its tip is now at 4")
        self.nodes[1].invalidateblock(self.nodes[1].getblockhash(5))
        assert_equal(self.nodes[1].getblockcount(), 4)
        self.log.info("Invalidate block 3 on node 2, so its tip is now 2")
        self.nodes[2].invalidateblock(self.nodes[2].getblockhash(3))
        assert_equal(self.nodes[2].getblockcount(), 2)
        self.log.info("..and then mine a block")
        self.generate(self.nodes[2], 1, sync_fun=self.no_op)
        self.log.info("Verify all nodes are at the right height")
        self.wait_until(lambda: self.nodes[2].getblockcount() == 3, timeout=5)
        self.wait_until(lambda: self.nodes[0].getblockcount() == 4, timeout=5)
        self.wait_until(lambda: self.nodes[1].getblockcount() == 4, timeout=5)
        self.nodes[0].reconsiderblock(badhash)  # Reset node0 so it can be reused later

        self.log.info("Verify that we reconsider all ancestors as well")
        blocks = self.generatetodescriptor(self.nodes[1], 10, ADDRESS_BCRT1_UNSPENDABLE_DESCRIPTOR, sync_fun=self.no_op)
        assert_equal(self.nodes[1].getbestblockhash(), blocks[-1])
        # Ensure the best-known header is synchronized with the active chain.
        assert_equal(self.nodes[1].getchainstates()['headers'], self.nodes[1].getblockcount())
        # Invalidate the two blocks at the tip
        self.nodes[1].invalidateblock(blocks[-1])
        self.nodes[1].invalidateblock(blocks[-2])
        assert_equal(self.nodes[1].getbestblockhash(), blocks[-3])
        # Verify that the best header is updated after invalidating a block.
        assert_equal(self.nodes[1].getchainstates()['headers'], self.nodes[1].getblockcount())

        # Reconsider only the previous tip
        self.nodes[1].reconsiderblock(blocks[-1])
        # Verify that the best header is updated after reconsidering a block.
        assert_equal(self.nodes[1].getchainstates()['headers'], self.nodes[1].getblockcount())

        # Should be back at the tip by now
        assert_equal(self.nodes[1].getbestblockhash(), blocks[-1])

        self.log.info("Verify that we reconsider all descendants")
        blocks = self.generatetodescriptor(self.nodes[1], 10, ADDRESS_BCRT1_UNSPENDABLE_DESCRIPTOR, sync_fun=self.no_op)
        assert_equal(self.nodes[1].getbestblockhash(), blocks[-1])
        # Invalidate the two blocks at the tip
        self.nodes[1].invalidateblock(blocks[-2])
        self.nodes[1].invalidateblock(blocks[-4])
        assert_equal(self.nodes[1].getbestblockhash(), blocks[-5])
        # Reconsider only the previous tip
        self.nodes[1].reconsiderblock(blocks[-4])
        # Should be back at the tip by now
        assert_equal(self.nodes[1].getbestblockhash(), blocks[-1])

        self.log.info("Verify that invalidating an unknown block throws an error")
        assert_raises_rpc_error(-5, "Block not found", self.nodes[1].invalidateblock, "00" * 32)
        assert_equal(self.nodes[1].getbestblockhash(), blocks[-1])

        self.log.info("Verify node updates best-known header after block invalidation/reconsideration")
        node0 = self.nodes[0]
        node1 = self.nodes[1]

        # Test Information
        # Active chain                --> 24  -> 25  ->  26  -> 27  -> 28  -> 29  -> 30
        # Fork chain (headers-only)   --> 24  -> 25' ->  26' -> 27' -> 28'
        # Expected behavior:
        # If block '27' is invalidated, the best header chain should be set at block 28', not 26.
        # If block '27' is reconsidered afterward, the best header chain should be reset to block 30.

        # Check that both nodes start at height 24 on the same chain
        assert node0.getblockcount() == node1.getblockcount() == 24
        assert_equal(node0.getbestblockhash(), node1.getbestblockhash())

        # Drop connections to prevent block propagation
        self.disconnect_nodes(0, 1)

        # Generate 4 blocks on node1 and cache their headers (this will be the fork)
        self.generatetodescriptor(node1, 4, ADDRESS_BCRT1_UNSPENDABLE_DESCRIPTOR, sync_fun=self.no_op)
        block_headers = []
        for i in range(node0.getblockcount() + 1, node1.getblockcount() + 1):
            header = from_hex(CBlockHeader(), node1.getblockheader(blockhash=node1.getblockhash(i), verbose=False))
            header.calc_sha256()
            block_headers.append(header)

        # Generate 6 blocks on node0 using a different address to create a different chain
        self.generatetoaddress(node0, 6, "bcrt1qthmht0k2qnh3wy7336z05lu2km7emzfpm3wg46", sync_fun=self.no_op)
        # Ensure that the nodes are on different chains
        assert node0.getblockhash(25) != node1.getblockhash(25)

        # Relay headers to node0
        peer0_conn = node0.add_p2p_connection(P2PInterface())
        headers_message = msg_headers()
        headers_message.headers = block_headers
        peer0_conn.send_message(headers_message)
        # Check that node0 only stored the headers
        self.wait_until(lambda: not try_rpc(-5, "Block not found", node0.getblockheader, block_headers[-1].hash))
        assert all(try_rpc(-1, "Block not found on disk", node0.getblock, header.hash) for header in block_headers)

        # Now that we are set, exercise the scenario.
        # There are two chains: Chain1 at block 28 on node1 and chain2 at block 30 on node0.
        # Invalidating node0's block 27 (chain2) will make node0 set its best-known header to chain1 block 28.
        # However, its tip will still be at chain2 because the node lacks blocks 27' and 28' data (only knows their headers).
        chain2_tip = node0.getbestblockhash()
        block_to_invalidate = node0.getblockhash(27)
        node0.invalidateblock(block_to_invalidate)
        assert_equal(node0.getchainstates()['headers'], 28)
        # But the active chain tip is still at block 26 (because we only have the header for block 27).
        assert_equal(node0.getbestblockhash(), node0.getblockhash(26))

        # Now, reconsider the invalidated block and verify that the node re-sets the best-known block header to the original block 30
        node0.reconsiderblock(block_to_invalidate)
        assert_equal(node0.getchainstates()['headers'], 30)
        assert_equal(node0.getbestblockhash(), chain2_tip)


if __name__ == '__main__':
    InvalidateTest().main()
