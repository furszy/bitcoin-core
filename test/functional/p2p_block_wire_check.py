#!/usr/bin/env python3
# Copyright (c) The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test that a block whose transactions do not match its commitments is rejected
from the wire, before the transactions are deserialized.

A full block's transactions are checked against the header's merkle root and the
coinbase's witness commitment straight from the serialized bytes. A mismatch is
rejected without expanding the (potentially witness-heavy) transactions in
memory, while a valid block is deserialized and processed as usual.
"""

from test_framework.blocktools import (
    COINBASE_MATURITY,
    NORMAL_GBT_REQUEST_PARAMS,
    add_witness_commitment,
    create_block,
)
from test_framework.messages import msg_block
from test_framework.p2p import P2PInterface
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal
from test_framework.wallet import MiniWallet


class BlockWireCheckTest(BitcoinTestFramework):
    def set_test_params(self):
        self.setup_clean_chain = True
        self.num_nodes = 1

    def build_block(self):
        """A solved block with a witness commitment, on top of the current tip."""
        tx = self.wallet.create_self_transfer()["tx"]
        block = create_block(tmpl=self.nodes[0].getblocktemplate(NORMAL_GBT_REQUEST_PARAMS), txlist=[tx])
        add_witness_commitment(block)
        block.solve()
        return block

    def run_test(self):
        node = self.nodes[0]
        self.wallet = MiniWallet(node)
        self.generate(self.wallet, COINBASE_MATURITY)

        # A valid block passes the wire check and is accepted as usual.
        peer = node.add_p2p_connection(P2PInterface())
        good_block = self.build_block()
        peer.send_and_ping(msg_block(good_block))
        assert_equal(node.getbestblockhash(), good_block.hash_hex)

        # Mutating a transaction's witness leaves every txid -- and so the
        # header's merkle root and proof of work -- untouched, but breaks the
        # coinbase's witness commitment. The wire check rejects it before
        # deserializing, where the transaction (txid) merkle root alone would
        # not catch it. The sender is punished exactly as the post-deserialization
        # mutation check would punish it.
        mutated = self.build_block()
        mutated.vtx[0].wit.vtxinwit[0].scriptWitness.stack = [b"\x11" * 32]

        attacker = node.add_p2p_connection(P2PInterface())
        with node.assert_debug_log(expected_msgs=["mutated block", "not deserializing"],
                                   unexpected_msgs=["bad-witness-merkle-match"]):
            attacker.send_without_ping(msg_block(mutated))
            attacker.wait_for_disconnect(timeout=5)
        # The mutated block was dropped; the tip did not move.
        assert_equal(node.getbestblockhash(), good_block.hash_hex)


if __name__ == '__main__':
    BlockWireCheckTest(__file__).main()
