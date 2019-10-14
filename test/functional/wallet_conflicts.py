#!/usr/bin/env python3
# Copyright (c) 2023 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""
Test that wallet correctly tracks transactions that have been conflicted by blocks, particularly during reorgs.
"""

from decimal import Decimal

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import (
        assert_equal,
)

class TxConflicts(BitcoinTestFramework):
    def add_options(self, parser):
        self.add_wallet_options(parser)

    def set_test_params(self):
        self.num_nodes = 3

    def skip_test_if_missing_module(self):
        self.skip_if_no_wallet()

    def run_test(self):
        self.log.info("Send tx from which to conflict outputs later")
        txid_conflict_from_1 = self.nodes[0].sendtoaddress(self.nodes[0].getnewaddress(), Decimal("10"))
        txid_conflict_from_2 = self.nodes[0].sendtoaddress(self.nodes[0].getnewaddress(), Decimal("10"))
        self.generate(self.nodes[0], 1)
        self.sync_blocks()

        self.log.info("Disconnect nodes to broadcast conflicts on their respective chains")
        self.disconnect_nodes(0, 1)
        self.disconnect_nodes(2, 1)

        self.log.info("Create a transaction with conflicted transactions spending outpoints A & B")
        nA = next(tx_out["vout"] for tx_out in self.nodes[0].gettransaction(txid_conflict_from_1)["details"] if tx_out["amount"] == Decimal("10"))
        nB = next(tx_out["vout"] for tx_out in self.nodes[0].gettransaction(txid_conflict_from_2)["details"] if tx_out["amount"] == Decimal("10"))
        inputs_tx_AB_0_parent = [{"txid": txid_conflict_from_1, "vout": nA}, {"txid": txid_conflict_from_2, "vout": nB}]
        inputs_tx_A_1 = [{"txid": txid_conflict_from_1, "vout": nA}]
        inputs_tx_B_1 = [{"txid": txid_conflict_from_2, "vout": nB}]

        outputs_tx_AB_0_parent = {self.nodes[0].getnewaddress(): Decimal("19.99998")}
        outputs_tx_A_1 = {self.nodes[0].getnewaddress(): Decimal("9.99998")}
        outputs_tx_B_1 = {self.nodes[0].getnewaddress(): Decimal("9.99998")}

        tx_AB_0_parent = self.nodes[0].signrawtransactionwithwallet(self.nodes[0].createrawtransaction(inputs_tx_AB_0_parent, outputs_tx_AB_0_parent))
        tx_A_1 = self.nodes[0].signrawtransactionwithwallet(self.nodes[0].createrawtransaction(inputs_tx_A_1, outputs_tx_A_1))
        tx_B_1 = self.nodes[0].signrawtransactionwithwallet(self.nodes[0].createrawtransaction(inputs_tx_B_1, outputs_tx_B_1))

        self.log.info("Broadcast conflicted transaction")
        conflicted_txid = self.nodes[0].sendrawtransaction(tx_AB_0_parent["hex"])
        self.generate(self.nodes[0], 1, sync_fun=self.no_op)

        # Build child conflicted tx
        C = next(tx_out["vout"] for tx_out in self.nodes[0].gettransaction(conflicted_txid)["details"] if tx_out["amount"] == Decimal("19.99998"))
        inputs_tx_C_child = [({"txid": conflicted_txid, "vout": C})]
        outputs_tx_C_child = {self.nodes[0].getnewaddress() : Decimal("19.99996")}
        tx_C_child = self.nodes[0].signrawtransactionwithwallet(self.nodes[0].createrawtransaction(inputs_tx_C_child, outputs_tx_C_child))
        tx_C_child_txid = self.nodes[0].sendrawtransaction(tx_C_child["hex"])
        self.generate(self.nodes[0], 1, sync_fun=self.no_op)

        self.log.info("Broadcast conflicting tx to node 1")
        conflicting_txid_A = self.nodes[1].sendrawtransaction(tx_A_1["hex"])
        self.generate(self.nodes[1], 4, sync_fun=self.no_op)
        conflicting_txid_B = self.nodes[1].sendrawtransaction(tx_B_1["hex"])
        self.generate(self.nodes[1], 4, sync_fun=self.no_op)

        # Reconnect node0 and node1 and check that conflicted_txid is effectively conflicted
        self.log.info("Connect nodes 0 and 1, and ensure that the tx is effectively conflicted")
        self.connect_nodes(0, 1)
        self.sync_blocks([self.nodes[0], self.nodes[1]])
        conflicted = self.nodes[0].gettransaction(conflicted_txid)
        tx_C_child = self.nodes[0].gettransaction(tx_C_child_txid)
        conflicting = self.nodes[0].gettransaction(conflicting_txid_A)
        # Conflicted tx should have confirmations set to the confirmations of the most conflicting tx
        assert_equal(conflicted["confirmations"], -conflicting["confirmations"])
        # Child should inherit conflicted state from parent
        assert_equal(tx_C_child["confirmations"], -conflicting["confirmations"])
        # Check the confirmations of the conflicting transactions
        assert_equal(conflicting["confirmations"], 8)
        assert_equal(self.nodes[0].gettransaction(conflicting_txid_B)["confirmations"], 4)

        # Node2 chain without conflicts
        self.generate(self.nodes[2], 15, sync_fun=self.no_op)

        # Connect node0 and node2 and wait reorg
        self.connect_nodes(0, 2)
        self.sync_blocks()
        conflicted = self.nodes[0].gettransaction(conflicted_txid)
        tx_C_child = self.nodes[0].gettransaction(tx_C_child_txid)

        self.log.info("Test that formerly conflicted transaction are inactive after a reorg")
        # Former conflicted tx should be unconfirmed as it hasn't been yet rebroadcast
        assert_equal(conflicted["confirmations"], 0)
        # Former conflicted child tx should be unconfirmed as it hasn't been rebroadcast
        assert_equal(tx_C_child["confirmations"], 0)
        # Rebroadcast former conflicted tx and check it confirms smoothly
        self.nodes[2].sendrawtransaction(conflicted["hex"])
        self.generate(self.nodes[2], 1)
        self.sync_blocks()
        former_conflicted = self.nodes[0].gettransaction(conflicted_txid)
        assert_equal(former_conflicted["confirmations"], 1)
        assert_equal(former_conflicted["blockheight"], 217)

if __name__ == '__main__':
    TxConflicts().main()
