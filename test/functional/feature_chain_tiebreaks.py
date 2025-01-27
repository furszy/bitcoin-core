#!/usr/bin/env python3
# Copyright (c) The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test that the correct active block is chosen in complex reorgs."""
from test.functional.test_framework.util import assert_greater_than
from test_framework.address import address_to_scriptpubkey
from test_framework.blocktools import create_block, create_coinbase
from test_framework.messages import CBlockHeader
from test_framework.p2p import P2PDataStore
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal

class ChainTiebreaksTest(BitcoinTestFramework):
    def add_options(self, parser):
        self.add_wallet_options(parser)
        
    def set_test_params(self):
        self.num_nodes = 2
        self.setup_clean_chain = True
        self.extra_args = [['-txindex'], []]

    @staticmethod
    def send_headers(node, blocks):
        """Submit headers for blocks to node."""
        for block in blocks:
            # Use RPC rather than P2P, to prevent the message from being interpreted as a block
            # announcement.
            node.submitheader(hexdata=CBlockHeader(block).serialize().hex())

    def test_chain_split_in_memory(self):
        node = self.nodes[0]
        # Add P2P connection to bitcoind
        peer = node.add_p2p_connection(P2PDataStore())

        self.log.info('Precomputing blocks')
        #
        #          /- B3 -- B7
        #        B1      \- B8
        #       /  \
        #      /    \ B4 -- B9
        #   B0           \- B10
        #      \
        #       \  /- B5
        #        B2
        #          \- B6
        #
        blocks = []

        # Construct B0, building off genesis.
        start_height = node.getblockcount()
        blocks.append(create_block(
            hashprev=int(node.getbestblockhash(), 16),
            tmpl={"height": start_height + 1}
        ))
        blocks[-1].solve()

        # Construct B1-B10.
        for i in range(1, 11):
            blocks.append(create_block(
                hashprev=int(blocks[(i - 1) >> 1].hash, 16),
                tmpl={
                    "height": start_height + (i + 1).bit_length(),
                    # Make sure each block has a different hash.
                    "curtime": blocks[-1].nTime + 1,
                }
            ))
            blocks[-1].solve()

        self.log.info('Make sure B0 is accepted normally')
        peer.send_blocks_and_test([blocks[0]], node, success=True)
        # B0 must be active chain now.
        assert_equal(node.getbestblockhash(), blocks[0].hash)

        self.log.info('Send B1 and B2 headers, and then blocks in opposite order')
        self.send_headers(node, blocks[1:3])
        peer.send_blocks_and_test([blocks[2]], node, success=True)
        peer.send_blocks_and_test([blocks[1]], node, success=False)
        # B2 must be active chain now, as full data for B2 was received first.
        assert_equal(node.getbestblockhash(), blocks[2].hash)

        self.log.info('Send all further headers in order')
        self.send_headers(node, blocks[3:])
        # B2 is still the active chain, headers don't change this.
        assert_equal(node.getbestblockhash(), blocks[2].hash)

        self.log.info('Send blocks B7-B10')
        peer.send_blocks_and_test([blocks[7]], node, success=False)
        peer.send_blocks_and_test([blocks[8]], node, success=False)
        peer.send_blocks_and_test([blocks[9]], node, success=False)
        peer.send_blocks_and_test([blocks[10]], node, success=False)
        # B2 is still the active chain, as B7-B10 have missing parents.
        assert_equal(node.getbestblockhash(), blocks[2].hash)

        self.log.info('Send parents B3-B4 of B8-B10 in reverse order')
        peer.send_blocks_and_test([blocks[4]], node, success=False, force_send=True)
        peer.send_blocks_and_test([blocks[3]], node, success=False, force_send=True)
        # B9 is now active. Despite B7 being received earlier, the missing parent.
        assert_equal(node.getbestblockhash(), blocks[9].hash)

        self.log.info('Invalidate B9-B10')
        node.invalidateblock(blocks[9].hash)
        node.invalidateblock(blocks[10].hash)
        # B7 is now active.
        assert_equal(node.getbestblockhash(), blocks[7].hash)

        # Invalidate blocks to start fresh on the next test
        node.invalidateblock(blocks[0].hash)

    def test_chain_split_from_disk(self):
        node = self.nodes[0]
        node.setmocktime(node.getblock(node.getblockhash(node.getblockcount()))["time"])

        node.createwallet(wallet_name="wallet", load_on_startup=True)
        wallet = node.get_wallet_rpc("wallet")

        peer = node.add_p2p_connection(P2PDataStore())

        self.log.info('Precomputing blocks')
        #
        #      A1
        #     /
        #   G
        #     \
        #      A2
        #
        blocks = []

        # Construct two blocks building from genesis.
        start_height = node.getblockcount()
        genesis_block = node.getblock(node.getblockhash(start_height))
        prev_time = genesis_block["time"]

        coinbase_script = address_to_scriptpubkey(wallet.getnewaddress())
        for i in range(0, 2):
            prev_time = prev_time + i + 1
            script_out = coinbase_script if i==0 else None
            blocks.append(create_block(
                hashprev=int(genesis_block["hash"], 16),
                coinbase=create_coinbase(height=start_height + 1, script_pubkey=script_out),
                tmpl={"height": start_height + 1,
                # Make sure each block has a different hash.
                "curtime": prev_time,
                }
            ))
            blocks[-1].solve()

        # Send blocks and test the last one is not connected
        self.log.info('Send A1 and A2. Make sure than only the former connects')
        peer.send_blocks_and_test([blocks[0]], node, success=True)
        peer.send_blocks_and_test([blocks[1]], node, success=False)
        node.syncwithvalidationinterfacequeue()

        # Verify we have balance.
        assert_greater_than(wallet.getbalances()['mine']['immature'], 0)
        # And verify we have two chains at the same height
        assert all(chain['height'] == 1 for chain in node.getchaintips())

        # Create a block on top of the prev_block_hash. block_height must be prev_block_height + 1.
        def make_block(prev_block_hash, block_height, script_pubkey=None):
            time = prev_time + 1 # Make sure each block has a different hash.
            ret_block = create_block(
                hashprev=prev_block_hash,
                coinbase=create_coinbase(height=block_height, script_pubkey=script_pubkey),
                tmpl={"height": block_height, "curtime": time}
            )
            ret_block.solve()
            return ret_block

        # Up to this point, there chain0 is the best chain. Both chains are at block height 1.
        assert_equal(node.getbestblockhash(), blocks[0].hash)
        # Now generate one more block for the second chain and make it the best chain.
        chain1_block1 = blocks[1]
        chain1_block2 = make_block(prev_block_hash=int(chain1_block1.hash, 16), block_height=start_height + 2)
        peer.send_blocks_and_test([chain1_block2], node, success=True, timeout=10)
        assert_equal(node.getbestblockhash(), chain1_block2.hash)

        # Assert block0 is no longer part of the best chain
        assert node.getblock(blocks[0].hash, verbose=1)['confirmations'] < 0

        # As the second chain is our best chain now, the coinbase tx in the first chain should have been abandoned now.
        assert_equal(wallet.gettransaction(blocks[0].vtx[0].hash)['details'][0]['abandoned'], True)

        # Up this point, we are at chain1_block2, let's generate another block at chain0
        chain0_block1 = blocks[0]
        chain0_block2 = make_block(prev_block_hash=int(chain0_block1.hash, 16), block_height=start_height + 2)
        peer.send_blocks_and_test([chain0_block2], node, success=False, timeout=10)

        # Verify the active chain is still the chain2 block, and not this one
        assert_equal(node.getbestblockhash(), chain1_block2.hash)
        assert_equal(wallet.getwalletinfo()['lastprocessedblock']['hash'], chain1_block2.hash)
        # Verify we have two chains at the same height
        assert all(chain['height'] == 2 for chain in node.getchaintips())
        assert_equal(wallet.getbalances()['mine']['immature'], 0)

        # At this point, chain1 is the active chain, and it has the same amount of work than chain0.
        # Restart node and see if chain0 becomes the active chain once more. And if that happens, create another
        # block in the second chain to trigger another reorg and cause the crash.

        self.log.info('Restart the node and check that the best tip before restarting matched the ones afterwards')
        # Restart and check enough times to this to eventually fail if the logic is broken
        happened = False
        for _ in range(15):
            self.restart_node(0, extra_args=['-checkblocks=0'])
            # Check the transaction is still abandoned upon restart
            wallet = node.get_wallet_rpc("wallet")
            assert_greater_than(wallet.getbalances()['mine']['immature'], 0)
            assert_equal(wallet.gettransaction(blocks[0].vtx[0].hash)['details'][0]['abandoned'], True)
            # If for some reason the first chain gets activated again, and become the main chain, this is an issue for the wallet
            if node.getbestblockhash() == chain0_block2.hash:
                # Make a block that will make the second chain the active chain again.
                peer = node.add_p2p_connection(P2PDataStore())
                prev_time = prev_time + 1
                chain1_block3 = make_block(prev_block_hash=int(chain1_block2.hash, 16), block_height=start_height + 3)
                peer.send_blocks_and_test([chain1_block3], node, success=True, timeout=10)
                node.syncwithvalidationinterfacequeue()
                assert False # no crash?

        assert happened # the crash did not happen.


    def run_test(self):
        #self.test_chain_split_in_memory()
        self.test_chain_split_from_disk()


if __name__ == '__main__':
    ChainTiebreaksTest(__file__).main()
