#!/usr/bin/env python3
# Copyright (c) 2014-2021 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test running bitcoind with -reindex and -reindex-chainstate options.

- Start a single node and generate 3 blocks.
- Stop the node and restart it with -reindex. Verify that the node has reindexed up to block 3.
- Stop the node and restart it with -reindex-chainstate. Verify that the node has reindexed up to block 3.
- Verify that out-of-order blocks are correctly processed, see LoadExternalBlockFile()
- Start a second node, generate blocks, then restart with -reindex after setting blk files to read-only
"""

import os
import time

from test_framework.test_framework import BitcoinTestFramework
from test_framework.p2p import MAGIC_BYTES
from test_framework.util import assert_equal
from test_framework.test_node import FailedToStartError

import subprocess


class ReindexTest(BitcoinTestFramework):
    def set_test_params(self):
        self.setup_clean_chain = True
        self.num_nodes = 2
        self.extra_args = [
            [],
            ["-fastprune"] # only used in reindex_readonly()
        ]

    def reindex(self, justchainstate=False):
        self.generatetoaddress(self.nodes[0], 3, self.nodes[0].get_deterministic_priv_key().address)
        blockcount = self.nodes[0].getblockcount()
        self.restart_node(0, extra_args=["-reindex-chainstate" if justchainstate else "-reindex"])
        self.connect_nodes(0, 1)
        assert_equal(self.nodes[0].getblockcount(), blockcount)  # start_node is blocking on reindex
        self.log.info("Success")

    # Check that blocks can be processed out of order
    def out_of_order(self):
        # The previous test created 12 blocks
        assert_equal(self.nodes[0].getblockcount(), 12)
        self.stop_node(0)

        # In this test environment, blocks will always be in order (since
        # we're generating them rather than getting them from peers), so to
        # test out-of-order handling, swap blocks 1 and 2 on disk.
        blk0 = os.path.join(self.nodes[0].datadir, self.nodes[0].chain, 'blocks', 'blk00000.dat')
        with open(blk0, 'r+b') as bf:
            # Read at least the first few blocks (including genesis)
            b = bf.read(2000)

            # Find the offsets of blocks 2, 3, and 4 (the first 3 blocks beyond genesis)
            # by searching for the regtest marker bytes (see pchMessageStart).
            def find_block(b, start):
                return b.find(MAGIC_BYTES["regtest"], start)+4

            genesis_start = find_block(b, 0)
            assert_equal(genesis_start, 4)
            b2_start = find_block(b, genesis_start)
            b3_start = find_block(b, b2_start)
            b4_start = find_block(b, b3_start)

            # Blocks 2 and 3 should be the same size.
            assert_equal(b3_start-b2_start, b4_start-b3_start)

            # Swap the second and third blocks (don't disturb the genesis block).
            bf.seek(b2_start)
            bf.write(b[b3_start:b4_start])
            bf.write(b[b2_start:b3_start])

        # The reindexing code should detect and accommodate out of order blocks.
        with self.nodes[0].assert_debug_log([
            'LoadExternalBlockFile: Out of order block',
            'LoadExternalBlockFile: Processing out of order child',
        ]):
            self.start_node(0, extra_args=["-reindex"])

        # All blocks should be accepted and processed.
        assert_equal(self.nodes[0].getblockcount(), 12)

    def reindex_readonly(self):
        self.connect_nodes(0, 1)
        addr = self.nodes[1].get_deterministic_priv_key().address

        # generate enough blocks to ensure that the -fastprune node fills up the
        # first blk00000.dat file and starts another block file

        # How big are empty regtest blocks?
        block_hash = self.generatetoaddress(self.nodes[1], 1, addr)[0]
        block_size = self.nodes[1].getblock(block_hash)["size"]
        block_size += 8 # BLOCK_SERIALIZATION_HEADER_SIZE

        # How many blocks do we need to roll over a new .blk file?
        block_count = self.nodes[1].getblockcount()
        fastprune_blockfile_size = 0x10000
        size_needed = fastprune_blockfile_size - (block_size * block_count)
        blocks_needed = size_needed // block_size

        self.log.debug("Generate enough blocks to start second block file")
        self.generatetoaddress(self.nodes[1], blocks_needed, addr)
        self.stop_node(1)

        assert os.path.exists(self.nodes[1].chain_path / 'blocks' / 'blk00000.dat')
        assert os.path.exists(self.nodes[1].chain_path / 'blocks' / 'blk00001.dat')

        self.log.debug("Make the first block file read-only")
        filename = self.nodes[1].chain_path / 'blocks' / 'blk00000.dat'
        subprocess.call(['chmod', '0444', filename])

        time.sleep(2)

        self.log.debug("Attempt to restart and reindex the node with the read-only block file")
        with self.nodes[1].assert_debug_log(expected_msgs=['FlushStateToDisk', 'failed to open file'], unexpected_msgs=[]):
            # Depending on the filesystem, attempted flushing to the read-only file will either happen...
            try:
                # ...during initialization...
                self.start_node(1, extra_args=["-reindex", "-fastprune"])
                # ...or upon shutdown, if initialization succeeds.
                self.stop_node(1)
            except FailedToStartError:
                # (failure occurred during initialization)
                pass
            finally:
                # Either way, ensure shutdown is complete
                self.nodes[1].wait_until_stopped(timeout=5)


    def run_test(self):
        self.reindex(False)
        self.reindex(True)
        self.reindex(False)
        self.reindex(True)

        self.out_of_order()

        self.reindex_readonly()

if __name__ == '__main__':
    ReindexTest().main()
