#!/usr/bin/env python3
# Copyright (c) 2024-present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://www.opensource.org/licenses/mit-license.php.

from test_framework.messages import (
    CBlockHeader,
    from_hex,
    msg_headers,
)
from test_framework.p2p import (
    P2PInterface,
)
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import (
    assert_equal,
)

# If this test passes, we have an issue syncing from AssumeUTXO peers.

class TestSyncFromAssumeUTXO(BitcoinTestFramework):

    def set_test_params(self):
        self.setup_clean_chain = True
        self.num_nodes = 3
        self.extra_args = [[], [], []]

    def setup_network(self):
        """Start with the nodes disconnected so that one can generate a snapshot
        including blocks the other hasn't yet seen."""
        self.add_nodes(self.num_nodes)
        self.start_nodes(extra_args=self.extra_args)

    def set_nodes_time(self, new_time):
        for node in self.nodes:
            node.setmocktime(new_time)

    def create_snapshot_chain(self, node_snapshot, nodes, num_blocks):
        # Mock time for a deterministic chain
        start_time = node_snapshot.getblockheader(node_snapshot.getbestblockhash())['time']
        for node in nodes:
            node.setmocktime(start_time)

        self.generate(node_snapshot, num_blocks, sync_fun=self.no_op)
        assert_equal(node_snapshot.getblockcount(), num_blocks)

        snapshot = node_snapshot.dumptxoutset(node_snapshot.datadir_path / "snapshot.dump")
        return snapshot

    def run_test(self):
        # Node0 creates the snapshot
        # Node1 runs AssumeUTXO. Receives the headers-chain and loads up the snapshot
        # Node2 starts clean and seeks up to sync from node1
        node0 = self.nodes[0]
        node1 = self.nodes[1]
        node2 = self.nodes[2]

        # Create snapshot
        snapshot = self.create_snapshot_chain(node0, self.nodes, num_blocks=500)
        snapshot_block_hash = snapshot['base_hash']

        # Now bury snapshot block with 500 more blocks.
        time = node0.getblockheader(node0.getbestblockhash())['time']
        self.set_nodes_time(time)
        for _ in range(50):
            self.generate(node0, 10, sync_fun=self.no_op)
            time += 60 * 60  # move one hour
            self.set_nodes_time(time)

        # Sync-up headers chain on node1 to load snapshot
        headers_provider_conn = node1.add_p2p_connection(P2PInterface())
        headers_provider_conn.wait_for_getheaders()
        msg = msg_headers()
        for block_num in range(1, 1001):
            msg.headers.append(from_hex(CBlockHeader(), node0.getblockheader(node0.getblockhash(block_num), verbose=False)))
        headers_provider_conn.send_message(msg)

        # Ensure headers arrived
        default_value = {'status': ''}  # No status
        headers_tip_hash = node0.getbestblockhash()
        self.wait_until(lambda: next(filter(lambda x: x['hash'] == headers_tip_hash, node1.getchaintips()), default_value)['status'] == "headers-only")

        # Load snapshot
        node1.loadtxoutset(snapshot['path'])
        # As the snapshot is always in the past, check the node is in IBD
        assert_equal(node1.getblockchaininfo()['initialblockdownload'], True)

        # Connect clean node2 to node1 and see if node2 requests the headers from it and if node1 respond to them.
        # If headers are relayed, node2 will request the full blocks and as node1 will not answer those requests,
        # node2 will stall for 10 minutes until the timeout triggers the disconnection.
        self.connect_nodes(2, 1)
        self.wait_until(lambda: next(filter(lambda x: x['hash'] == snapshot_block_hash, node2.getchaintips()), default_value)['status'] == "headers-only")

        # If headers were received, we know for sure that node2 requested the historical blocks to the not-yet-synced
        # AssumeUTXO peer. Which is bad... because, node1 does not have any block data, so it will ignore the getdata
        # block requests which will cause disconnection after 10 minutes due to node1's perceived unresponsiveness from
        # node2 perspective.
        assert len(node2.getpeerinfo()[0]['inflight']) > 0

        # Verify it happens by moving the time forward 10 minutes, node2 will disconnect the honest node1.
        self.set_nodes_time(time + 60 * 10 + 1)
        self.wait_until(lambda: len(node2.getpeerinfo()) == 0)  # --> ISSUE VERIFIED.

        # Result: two honest peers disconnected from each other due to an historical block request.


if __name__ == '__main__':
    TestSyncFromAssumeUTXO().main()