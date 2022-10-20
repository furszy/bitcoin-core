#!/usr/bin/env python3
# Copyright (c) 2022 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://www.opensource.org/licenses/mit-license.php.

"""Test that we don't get stalled requesting headers from an empty/un-synced peer,
   or a peer that isn't providing us useful info on the getheaders response.
"""

from test_framework.test_framework import BitcoinTestFramework

class SyncTest(BitcoinTestFramework):
    def set_test_params(self):
        self.setup_clean_chain = True
        self.num_nodes = 3
        self.extra_args = [[], [], []]

    def is_chain_sync(self, node, expected_chain_height):
        chain_tips = node.getchaintips()
        for chain in chain_tips:
            if chain['status'] == "headers-only" or chain['status'] == "active":
                if chain['height'] == expected_chain_height:
                    return True
        return False

    def run_test(self):
        # Disconnect nodes
        self.disconnect_nodes(1, 0)

        self.log.info("Generate blocks on node0 only..")
        num_of_blocks = 300
        self.generate(self.nodes[0], num_of_blocks, sync_fun=self.no_op)

        # Context:
        #   As node2 has no blocks and it's the only connection that node1 has, node1 should have sent the getheaders
        #   request to node2, and node2 should have responded with an empty headers message.
        #   So, node1 shouldn't have the sync process state as "started" (cannot request anything from node2).
        #   So, when node0 gets connected to node1, node1 should automatically trigger the sync process and actively
        #   sync up the chain.
        self.log.info("Connect node1 to node0 and wait for sync..")
        self.connect_nodes(1, 0)
        self.wait_until(lambda: self.is_chain_sync(self.nodes[1], self.nodes[0].getblockcount()))


if __name__ == '__main__':
    SyncTest().main()
