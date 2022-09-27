#!/usr/bin/env python3
# Copyright (c) 2022 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://www.opensource.org/licenses/mit-license.php.

"""
Test wallet filters update by calling 'getwalletfilter' RPC command
"""

from test_framework.test_framework import BitcoinTestFramework


class WalletFiltersTest(BitcoinTestFramework):
    def add_options(self, parser):
        self.add_wallet_options(parser, legacy=False)

    def skip_test_if_missing_module(self):
        self.skip_if_no_wallet()

    def set_test_params(self):
        self.setup_clean_chain = True
        self.num_nodes = 2
        self.extra_args = [["-blockfilterindex=1", "-peerblockfilters"], ["-blockfilterindex=1", "-peerblockfilters"]]

    def run_test(self):
        self.nodes[1].createwallet(wallet_name='w1', descriptors=self.options.descriptors)
        w1 = self.nodes[1].get_wallet_rpc('w1')

        self.log.info("Checking getwalletfilters..")
        # All filters have range_end=1 (context: default bitcoin.conf keypool=1)
        keypool_size = 1
        for obj in w1.getwalletfilters():
            assert obj["range_end"] == keypool_size

        # Create addresses and assert elements update.
        addresses_count = 10
        for _ in range(addresses_count):
            w1.getnewaddress(label="", address_type="bech32")
        w1.syncwithvalidationinterfacequeue()

        # At least one spkm should have range_end=ADDRESSES_COUNT.
        assert any(obj["range_end"] == addresses_count for obj in w1.getwalletfilters())

        # todo: would be nice to add a membership test here.
        #  craft a tx inside the wallet, then create a block outside of the node and
        #  check that the block filter verifies against the wallet filter.

if __name__ == '__main__':
    WalletFiltersTest(__file__).main()

