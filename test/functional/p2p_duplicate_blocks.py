#!/usr/bin/env python3
# Copyright (c) The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test that blocks we already have are dropped before deserialization.

Once a block's transactions are stored, receiving the block again gains us
nothing. The node recognizes it from the header alone -- which it reads
before the transactions -- and drops it without deserializing the rest. This
file groups those cases by the message that carries the block."""

from test_framework.blocktools import create_block
from test_framework.messages import msg_block
from test_framework.p2p import P2PInterface
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal


class DuplicateBlocksTest(BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 1

    def run_test(self):
        self.generate(self.nodes[0], 1, sync_fun=self.no_op)  # leave IBD
        self.test_duplicate_full_block()

    def new_block_on_tip(self, node):
        """A solved block building on the node's current tip."""
        tip = int(node.getbestblockhash(), 16)
        height = node.getblockcount() + 1
        block = create_block(tip, height=height, ntime=node.getblock(node.getbestblockhash())["time"] + 1)
        block.solve()
        return block

    def test_duplicate_full_block(self):
        self.log.info("A full block we already have is dropped before deserialization")
        node = self.nodes[0]
        peer = node.add_p2p_connection(P2PInterface())
        block = self.new_block_on_tip(node)

        # First delivery: accepted and stored as the new tip.
        peer.send_and_ping(msg_block(block))
        assert_equal(node.getbestblockhash(), block.hash_hex)

        # Second delivery of the same block: we already have its transactions,
        # so it is dropped before they are deserialized. A duplicate is not
        # misbehavior, so the peer is not disconnected.
        with node.assert_debug_log([f"already have block {block.hash_hex} from peer"]):
            peer.send_and_ping(msg_block(block))
        assert peer.is_connected
        assert_equal(node.getbestblockhash(), block.hash_hex)


if __name__ == '__main__':
    DuplicateBlocksTest(__file__).main()
