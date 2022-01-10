#!/usr/bin/env python3
# Copyright (c) 2021 The PIVX Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test deterministic masternodes"""

import time

from test_framework.test_framework import PivxTestFramework
from test_framework.util import (
    assert_equal,
    connect_nodes_clique,
    wait_until,
)


class DkgPoseTest(PivxTestFramework):

    def set_test_params(self):
        # 1 miner, 1 controller, 6 remote mns
        self.num_nodes = 8
        self.minerPos = 0
        self.controllerPos = 1
        self.setup_clean_chain = True
        self.extra_args = [["-nuparams=v5_shield:1", "-nuparams=v6_evo:130", "-debug=llmq", "-debug=dkg", "-debug=net"]] * self.num_nodes
        self.extra_args[0].append("-sporkkey=932HEevBSujW2ud7RfB1YF91AFygbBRQj3de3LyaCRqNzKKgWXi")

    def add_new_dmn(self, strType, op_keys=None, from_out=None):
        self.mns.append(self.register_new_dmn(2 + len(self.mns),
                                             self.minerPos,
                                             self.controllerPos,
                                             strType,
                                             outpoint=from_out,
                                             op_blskeys=op_keys))

    def check_mn_list(self):
        for i in range(self.num_nodes):
            self.check_mn_list_on_node(i, self.mns)
        self.log.info("Deterministic list contains %d masternodes for all peers." % len(self.mns))

    def check_mn_enabled_count(self, enabled, total):
        for node in self.nodes:
            node_count = node.getmasternodecount()
            assert_equal(node_count['enabled'], enabled)
            assert_equal(node_count['total'], total)

    def wait_until_mnsync_completed(self):
        SYNC_FINISHED = [999] * self.num_nodes
        synced = [-1] * self.num_nodes
        timeout = time.time() + 120
        while synced != SYNC_FINISHED and time.time() < timeout:
            synced = [node.mnsync("status")["RequestedMasternodeAssets"]
                      for node in self.nodes]
            if synced != SYNC_FINISHED:
                time.sleep(5)
        if synced != SYNC_FINISHED:
            raise AssertionError("Unable to complete mnsync: %s" % str(synced))

    def disable_network_for_node(self, node):
        node.setnetworkactive(False)
        wait_until(lambda: node.getconnectioncount() == 0)

    def setup_test(self):
        self.mns = []
        self.disable_mocktime()
        connect_nodes_clique(self.nodes)

        # Enforce mn payments and reject legacy mns at block 131
        self.activate_spork(0, "SPORK_8_MASTERNODE_PAYMENT_ENFORCEMENT")
        assert_equal("success", self.set_spork(self.minerPos, "SPORK_21_LEGACY_MNS_MAX_HEIGHT", 130))
        time.sleep(1)
        assert_equal([130] * self.num_nodes, [self.get_spork(x, "SPORK_21_LEGACY_MNS_MAX_HEIGHT")
                                              for x in range(self.num_nodes)])

        # Mine 130 blocks
        self.log.info("Mining...")
        self.nodes[self.minerPos].generate(10)
        self.sync_blocks()
        self.wait_until_mnsync_completed()
        self.nodes[self.minerPos].generate(120)
        self.sync_blocks()
        self.assert_equal_for_all(130, "getblockcount")

        # enabled/total masternodes: 0/0
        self.check_mn_enabled_count(0, 0)

        # Create 6 DMNs and init the remote nodes
        self.log.info("Initializing masternodes...")
        for _ in range(2):
            self.add_new_dmn("internal")
            self.add_new_dmn("external")
            self.add_new_dmn("fund")
        assert_equal(len(self.mns), 6)
        for mn in self.mns:
            self.nodes[mn.idx].initmasternode(mn.operator_sk, "", True)
            time.sleep(1)
        self.nodes[self.minerPos].generate(1)
        self.sync_blocks()

        # enabled/total masternodes: 6/6
        self.check_mn_enabled_count(6, 6)
        self.check_mn_list()

        # Check status from remote nodes
        assert_equal([self.nodes[idx].getmasternodestatus()['status'] for idx in range(2, self.num_nodes)],
                     ["Ready"] * (self.num_nodes - 2))
        self.log.info("All masternodes ready.")


    def run_test(self):
        miner = self.nodes[self.minerPos]

        # initialize and start masternodes
        self.setup_test()
        assert_equal(len(self.mns), 6)

        # Mine a LLMQ final commitment regularly with 3 signers
        _, bad_mnode = self.mine_quorum()
        assert_equal(171, miner.getblockcount())
        assert bad_mnode is None

        # Mine the next final commitment after disconnecting a member
        _, bad_mnode = self.mine_quorum(invalidate_func=self.disable_network_for_node,
                                        skip_bad_member_sync=True)
        assert_equal(191, miner.getblockcount())
        assert bad_mnode is not None

        # Check PoSe
        self.log.info("Check that node %d has been PoSe punished..." % bad_mnode.idx)
        expected_penalty = 66
        assert_equal(expected_penalty, miner.listmasternodes(bad_mnode.proTx)[0]["dmnstate"]["PoSePenalty"])
        self.log.info("Node punished.")
        # penalty decreases at every block
        miner.generate(1)
        self.sync_all([n for i, n in enumerate(self.nodes) if i != bad_mnode.idx])
        expected_penalty -= 1
        assert_equal(expected_penalty, miner.listmasternodes(bad_mnode.proTx)[0]["dmnstate"]["PoSePenalty"])

        # Keep mining commitments until the bad node is banned
        timeout = time.time() + 600
        while time.time() < timeout:
            self.mine_quorum(invalidated_idx=bad_mnode.idx, skip_bad_member_sync=True)
            pose_height = miner.listmasternodes(bad_mnode.proTx)[0]["dmnstate"]["PoSeBanHeight"]
            if pose_height != -1:
                self.log.info("Node %d has been PoSeBanned at height %d" % (bad_mnode.idx, pose_height))
                self.log.info("All good.")
                return
            time.sleep(1)
        # timeout
        raise Exception("Node not banned after 10 minutes")



if __name__ == '__main__':
    DkgPoseTest().main()
