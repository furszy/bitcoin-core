#!/usr/bin/env python3
# Copyright (c) 2021 The PIVX Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://www.opensource.org/licenses/mit-license.php.
"""Test MN quorum connection flows"""

import time

from test_framework.test_framework import PivxTestFramework
from test_framework.mininode import P2PInterface
from test_framework.messages import msg_version
from random import getrandbits
from test_framework.util import (
    assert_equal,
    assert_true,
    bytes_to_hex_str,
    connect_nodes_clique,
    hash256,
    hex_str_to_bytes,
    wait_until,
)

class TestP2PConn(P2PInterface):
    def on_version(self, message):
        pass

class DMNConnectionTest(PivxTestFramework):

    def set_test_params(self):
        # 1 miner, 1 controller, 6 remote dmns
        self.num_nodes = 8
        self.minerPos = 0
        self.controllerPos = 1
        self.setup_clean_chain = True
        self.extra_args = [["-nuparams=v5_shield:1", "-nuparams=v6_evo:101"]] * self.num_nodes
        self.extra_args[0].append("-sporkkey=932HEevBSujW2ud7RfB1YF91AFygbBRQj3de3LyaCRqNzKKgWXi")

    def add_new_dmn(self, mns, strType, op_keys=None, from_out=None):
        mn = self.register_new_dmn(2 + len(mns),
                                   self.minerPos,
                                   self.controllerPos,
                                   strType,
                                   outpoint=from_out,
                                   op_blskeys=op_keys)
        mns.append(mn)
        return mn

    def check_mn_enabled_count(self, enabled, total):
        for node in self.nodes:
            node_count = node.getmasternodecount()
            assert_equal(node_count['enabled'], enabled)
            assert_equal(node_count['total'], total)

    def wait_until_mnsync_completed(self):
        SYNC_FINISHED = [999] * self.num_nodes
        synced = [-1] * self.num_nodes
        timeout = time.time() + 160
        while synced != SYNC_FINISHED and time.time() < timeout:
            synced = [node.mnsync("status")["RequestedMasternodeAssets"]
                      for node in self.nodes]
            if synced != SYNC_FINISHED:
                time.sleep(5)
        if synced != SYNC_FINISHED:
            raise AssertionError("Unable to complete mnsync: %s" % str(synced))

    def setup_phase(self):
        # Disconnect every node and generate connections to all of them manually.
        for node in self.nodes:
            self.disconnect_peers(node)
        connect_nodes_clique(self.nodes)
        self.check_peers_count(14)

        # Mine 110 blocks
        self.log.info("Mining...")
        self.miner.generate(110)
        assert_equal("success", self.set_spork(self.minerPos, "SPORK_21_LEGACY_MNS_MAX_HEIGHT", 105))
        self.sync_blocks()
        self.assert_equal_for_all(110, "getblockcount")

        # -- DIP3 enforced and SPORK_21 active here --
        self.wait_until_mnsync_completed()

        # Create 6 DMNs and init the remote nodes
        for i in range(6):
            mn = self.add_new_dmn(self.mns, "fund")
            self.nodes[mn.idx].initmasternode(mn.operator_sk, "", True)
            time.sleep(1)
        self.miner.generate(1)
        self.sync_blocks()

        # enabled/total masternodes: 6/6
        self.check_mn_enabled_count(6, 6)
        # Check status from remote nodes
        assert_equal([self.nodes[idx].getmasternodestatus()['status'] for idx in range(2, self.num_nodes)],
                     ["Ready"] * (self.num_nodes - 2))
        self.log.info("All masternodes ready")

    def disconnect_peers(self, node):
        node.setnetworkactive(False)
        time.sleep(3)
        assert_equal(len(node.getpeerinfo()), 0)
        node.setnetworkactive(True)

    def check_peers_count(self, expected_count):
        for i in range(0, 7):
            assert_equal(len(self.nodes[i].getpeerinfo()), expected_count)

    def check_peer_info(self, peer_info, mn, is_iqr_conn, inbound = False):
        assert_equal(peer_info["masternode"], True)
        assert_equal(peer_info["verif_mn_proreg_tx_hash"], mn.proTx)
        assert_equal(peer_info["verif_mn_operator_pubkey_hash"], bytes_to_hex_str(hash256(hex_str_to_bytes(mn.operator_pk))))
        assert_equal(peer_info["masternode_iqr_conn"], is_iqr_conn)
        # An inbound connection has obviously a different internal port.
        if not inbound:
            assert_equal(peer_info["addr"], mn.ipport)

    def check_peers_info(self, peers_info, quorum_members, is_iqr_conn, inbound = False):
        for quorum_node in quorum_members:
            found = False
            for peer in peers_info:
                if "verif_mn_proreg_tx_hash" in peer and peer["verif_mn_proreg_tx_hash"] == quorum_node.proTx:
                    self.check_peer_info(peer, quorum_node, is_iqr_conn, inbound)
                    found = True
                    break
            if not found:
                print(peers_info)
            assert_true(found, "MN connection not found for ip: " + str(quorum_node.ipport))

    def has_mn_auth_connection(self, node, expected_proreg_tx_hash):
        peer_info = node.getpeerinfo()
        return (len(peer_info) == 1) and (peer_info[0]["verif_mn_proreg_tx_hash"] == expected_proreg_tx_hash)

    def run_test(self):
        self.disable_mocktime()
        self.miner = self.nodes[self.minerPos]
        self.mns = []
        # Create and start 6 DMN
        self.setup_phase()

        ##############################################################
        # 1) Disconnect peers from DMN and add a direct DMN connection
        ##############################################################
        self.log.info("1) Testing single DMN connection, disconnecting nodes..")
        mn1 = self.mns[0]
        mn1_node = self.nodes[mn1.idx]
        self.disconnect_peers(mn1_node)

        self.log.info("disconnected, connecting to a single DMN and auth him..")
        # Now try to connect to the second DMN only
        mn2 = self.mns[1]
        assert mn1_node.mnconnect("single_conn", [mn2.proTx])
        wait_until(lambda: self.has_mn_auth_connection(mn1_node, mn2.proTx), timeout=60)
        peer_info = mn1_node.getpeerinfo()[0]
        # Check connected peer info: same DMN and mnauth succeeded
        self.check_peer_info(peer_info, mn2, is_iqr_conn=False)
        # Same for the the other side
        mn2_node = self.nodes[mn2.idx]
        peers_info = mn2_node.getpeerinfo()
        self.check_peers_info(peers_info, [mn1], is_iqr_conn=False, inbound=True)
        self.log.info("Completed DMN-to-DMN authenticated connection!")

        ################################################################
        # 2) Disconnect peers from DMN and add quorum members connection
        ################################################################
        self.log.info("2) Testing quorum connections, disconnecting nodes..")
        mn3 = self.mns[2]
        mn4 = self.mns[3]
        mn5 = self.mns[4]
        mn6 = self.mns[5]
        quorum_nodes = [mn3, mn4, mn5, mn6]
        self.disconnect_peers(mn2_node)
        self.log.info("disconnected, connecting to quorum members..")
        quorum_members = [mn2.proTx, mn3.proTx, mn4.proTx, mn5.proTx, mn6.proTx]
        assert mn2_node.mnconnect("quorum_members_conn", quorum_members, 1, mn2_node.getbestblockhash())
        # Check connected peer info: same quorum members and mnauth succeeded
        wait_until(lambda: len(mn2_node.getpeerinfo()) == 4, timeout=90)
        time.sleep(5) # wait a bit more to receive the mnauth
        peers_info = mn2_node.getpeerinfo()
        self.check_peers_info(peers_info, quorum_nodes, is_iqr_conn=False)
        # Same for the other side (MNs receiving the new connection)
        for mn_node in [self.nodes[mn3.idx], self.nodes[mn4.idx], self.nodes[mn5.idx], self.nodes[mn6.idx]]:
            self.check_peers_info(mn_node.getpeerinfo(), [mn2], is_iqr_conn=False, inbound=True)
        self.log.info("Completed DMN-to-quorum connections!")

        ##################################################################################
        # 3) Update already connected quorum members in (2) to be intra-quorum connections
        ##################################################################################
        self.log.info("3) Testing connections update to be intra-quorum relay connections")
        assert mn2_node.mnconnect("iqr_members_conn", quorum_members, 1, mn2_node.getbestblockhash())
        peers_info = mn2_node.getpeerinfo()
        self.check_peers_info(peers_info, quorum_nodes, is_iqr_conn=True)
        # Same for the other side (MNs receiving the new connection)
        for mn_node in [self.nodes[mn3.idx], self.nodes[mn4.idx], self.nodes[mn5.idx], self.nodes[mn6.idx]]:
            assert mn_node.mnconnect("iqr_members_conn", quorum_members, 1, mn2_node.getbestblockhash())
            self.check_peers_info(mn_node.getpeerinfo(), [mn2], is_iqr_conn=True, inbound=True)
        self.log.info("Completed update to quorum relay members!")

        ###########################################
        # 4) Now test the connections probe process
        ###########################################
        self.log.info("4) Testing MN probe connection process..")
        # Take mn6, disconnect all the nodes and try to probe connection to one of them
        mn6_node = self.nodes[mn6.idx]
        self.disconnect_peers(mn6_node)
        self.log.info("disconnected, probing MN connection..")
        with mn6_node.assert_debug_log(["Masternode probe successful for " + mn5.proTx]):
            assert mn_node.mnconnect("probe_conn", [mn5.proTx])
            time.sleep(10) # wait a bit until the connection gets established
        self.log.info("Completed MN connection probe!")

        ###############################################################################
        # 5) Now test regular node disconnecting after receiving an auth DMN connection
        ###############################################################################
        self.log.info("5) Testing regular node disconnection after receiving an auth DMN connection..")
        self.disconnect_peers(self.miner)
        no_version_node = self.miner.add_p2p_connection(TestP2PConn(), send_version=False, wait_for_verack=False)
        assert_equal(len(self.miner.getpeerinfo()), 1)
        # send the version as it would be a MN
        mn_challenge = getrandbits(256)
        with self.miner.assert_debug_log(["but we're not a masternode, disconnecting"]):
            no_version_node.send_message(msg_version(mn_challenge))
            time.sleep(2)
        # as the miner is not a DMN, the miner should had dropped the connection.
        assert_equal(len(self.miner.getpeerinfo()), 0)
        self.log.info("Regular node disconnected auth connection successfully")


if __name__ == '__main__':
    DMNConnectionTest().main()


