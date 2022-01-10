#!/usr/bin/env python3
# Copyright (c) 2021 The PIVX Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test deterministic masternodes"""

import time

from test_framework.test_framework import PivxTestFramework
from test_framework.util import (
    assert_greater_than,
    assert_equal,
    connect_nodes_clique,
)


class DkgTest(PivxTestFramework):

    def set_test_params(self):
        # 1 miner, 1 controller, 6 remote mns
        self.num_nodes = 8
        self.minerPos = 0
        self.controllerPos = 1
        self.setup_clean_chain = True
        self.extra_args = [["-nuparams=v5_shield:1", "-nuparams=v6_evo:130", "-debug=llmq", "-debug=dkg", "-debug=net"]] * self.num_nodes
        self.extra_args[0].append("-sporkkey=932HEevBSujW2ud7RfB1YF91AFygbBRQj3de3LyaCRqNzKKgWXi")

    def add_new_dmn(self, mns, strType, op_keys=None, from_out=None):
        mns.append(self.register_new_dmn(2 + len(mns),
                                         self.minerPos,
                                         self.controllerPos,
                                         strType,
                                         outpoint=from_out,
                                         op_blskeys=op_keys))

    def check_mn_list(self, mns):
        for i in range(self.num_nodes):
            self.check_mn_list_on_node(i, mns)
        self.log.info("Deterministic list contains %d masternodes for all peers." % len(mns))

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

    def blocks_to_dkg_start(self):
        node = self.nodes[self.minerPos]
        curr_block = node.getblockcount()
        session_blocks = curr_block % 60
        if session_blocks == 0:
            return 0
        return 60 - session_blocks

    def disconnect_peers(self, node):
        node.setnetworkactive(False)
        time.sleep(3)
        assert_equal(len(node.getpeerinfo()), 0)
        node.setnetworkactive(True)

    def get_quorum_members(self, mns, quorum_hash):
        members = []
        # preserve getquorummembers order
        for protx in self.nodes[0].getquorummembers(100, quorum_hash):
            members.append(next(mn for mn in mns if mn.proTx == protx))
        return members

    def check_dkg_phase(self, mn, phase, bad_nodes):
        assert_greater_than(bad_nodes, -1)
        good_nodes = 3 - bad_nodes
        assert_greater_than(good_nodes, -1)
        s = self.nodes[mn.idx].quorumdkgstatus(2)['session']['llmq_test']
        assert_equal(s['phase'], phase)
        assert_equal(s['sentContributions'], 0 if phase == 1 else 1)
        assert_equal(s['sentComplaint'], 0 if phase <= 2 else bad_nodes)
        assert_equal(s['sentJustification'], 0)
        assert_equal(s['sentPrematureCommitment'], phase > 4)
        assert_equal(len(s['receivedContributions']), 0 if phase == 1 else good_nodes)
        assert_equal(len(s['receivedComplaints']), 0 if phase <= 2 else (bad_nodes * good_nodes))
        assert_equal(len(s['receivedJustifications']), 0)
        assert_equal(len(s['receivedPrematureCommitments']), 0 if phase <= 4 else good_nodes)

    def check_final_commitment(self, qfc, valid, signers):
        signersCount = 0
        signersBitStr = 0
        for i, s in enumerate(signers):
            signersCount += s
            signersBitStr += (s << i)
        signersBitStr = "0%d" % signersBitStr
        validCount = 0
        validBitStr = 0
        for i, s in enumerate(valid):
            validCount += s
            validBitStr += (s << i)
        validBitStr = "0%d" % validBitStr
        assert_equal(qfc['version'], 1)
        assert_equal(qfc['llmqType'], 100)
        assert_equal(qfc['signersCount'], signersCount)
        assert_equal(qfc['signers'], signersBitStr)
        assert_equal(qfc['validMembersCount'], validCount)
        assert_equal(qfc['validMembers'], validBitStr)

    def setup_test(self, mns):
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
            self.add_new_dmn(mns, "internal")
            self.add_new_dmn(mns, "external")
            self.add_new_dmn(mns, "fund")
        assert_equal(len(mns), 6)
        for mn in mns:
            self.nodes[mn.idx].initmasternode(mn.operator_sk, "", True)
            time.sleep(1)
        self.nodes[self.minerPos].generate(1)
        self.sync_blocks()

        # enabled/total masternodes: 6/6
        self.check_mn_enabled_count(6, 6)
        self.check_mn_list(mns)

        # Check status from remote nodes
        assert_equal([self.nodes[idx].getmasternodestatus()['status'] for idx in range(2, self.num_nodes)],
                     ["Ready"] * (self.num_nodes - 2))
        self.log.info("All masternodes ready.")


    def run_test(self):
        miner = self.nodes[self.minerPos]

        # initialize and start masternodes
        mns = []
        self.setup_test(mns)

        # Test DKG phases (starts at block 180)
        self.log.info("Testing DKG...")
        miner.generate(self.blocks_to_dkg_start() + 1)
        self.sync_blocks()
        self.assert_equal_for_all(181, "getblockcount")
        quorum_hash = miner.getblockhash(180)
        quorum = self.get_quorum_members(mns, quorum_hash)
        self.log.info("members: %s" % str([m.idx for m in quorum]))
        assert_equal(len(quorum), 3)
        for phase in range(1, 7):
            self.log.info("Phase %d (block %d)" % (phase, miner.getblockcount()))
            for m in quorum:
                self.check_dkg_phase(m, phase, 0)
            if phase < 6:
                miner.generate(6 if phase < 5 else 5)
                self.sync_all()
            time.sleep(5)
        self.assert_equal_for_all(210, "getblockcount")
        for m in quorum:
            mc = self.nodes[m.idx].quorumdkgstatus(2)['minableCommitments']
            assert_equal(len(mc), 1)
            assert_equal(mc['llmq_test']['quorumHash'], quorum_hash)
        # mine final commitment
        time.sleep(2)
        miner.generate(2)
        self.sync_all()
        # check mined commitment
        qfc = miner.getminedcommitment(100, quorum_hash)
        self.check_final_commitment(qfc, valid=[1, 1, 1], signers=[1, 1, 1])
        blk = miner.getblock(qfc['block_hash'], True)['height']
        assert_greater_than(blk, 209)
        self.log.info("Final commitment correctly mined on chain")

        # New round starts at block 240
        self.log.info("Mining...")
        miner.generate(self.blocks_to_dkg_start() + 1)
        self.sync_blocks()
        self.assert_equal_for_all(241, "getblockcount")

        # New DKG round (disconnect third member)
        self.log.info("New DKG...")
        quorum_hash = miner.getblockhash(240)
        quorum = self.get_quorum_members(mns, quorum_hash)
        self.log.info("members: %s" % str([m.idx for m in quorum]))
        assert_equal(len(quorum), 3)
        bad_mnode = quorum.pop()
        bad_node = self.nodes[bad_mnode.idx]
        self.disconnect_peers(bad_node)
        nodes_to_sync = [n for n in self.nodes if n is not bad_node]
        self.log.info("Disconnected node %d" % bad_mnode.idx)
        assert_equal(len(quorum), 2)
        for phase in range(1, 7):
            self.log.info("Phase %d (block %d)" % (phase, miner.getblockcount()))
            for m in quorum:
                self.check_dkg_phase(m, phase, 1)
            if phase < 6:
                miner.generate(6 if phase < 5 else 5)
                self.sync_all(nodes_to_sync)
            time.sleep(5)
        assert_equal(270, miner.getblockcount())
        for m in quorum:
            mc = self.nodes[m.idx].quorumdkgstatus(2)['minableCommitments']
            assert_equal(len(mc), 1)
            assert_equal(mc['llmq_test']['quorumHash'], quorum_hash)
        # mine final commitment
        time.sleep(2)
        miner.generate(2)
        self.sync_all(nodes_to_sync)
        # check mined commitment
        qfc = miner.getminedcommitment(100, quorum_hash)
        self.check_final_commitment(qfc, valid=[1, 1, 0], signers=[1, 1, 0])
        blk = miner.getblock(qfc['block_hash'], True)['height']
        assert_greater_than(blk, 269)
        self.log.info("Final commitment correctly mined on chain")
        # Check PoSe
        self.log.info("Check that node %d has been PoSe punished..." % bad_mnode.idx)
        expected_penaly = 66 - (miner.getblockcount() - blk)
        assert_equal(expected_penaly, miner.listmasternodes(bad_mnode.proTx)[0]["dmnstate"]["PoSePenalty"])
        # penalty decreases at every block
        miner.generate(1)
        self.sync_all(nodes_to_sync)
        expected_penaly -= 1
        assert_equal(expected_penaly, miner.listmasternodes(bad_mnode.proTx)[0]["dmnstate"]["PoSePenalty"])

        self.log.info("All good.")


if __name__ == '__main__':
    DkgTest().main()
