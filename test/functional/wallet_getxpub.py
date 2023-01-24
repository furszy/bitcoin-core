#!/usr/bin/env python3
# Copyright (c) 2023 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test wallet getxpub RPC."""

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import (
    assert_equal,
    assert_raises_rpc_error,
)
from test_framework.wallet_util import WalletUnlock


class WalletGetXpubTest(BitcoinTestFramework):
    def add_options(self, parser):
        self.add_wallet_options(parser, descriptors=True, legacy=False)

    def set_test_params(self):
        self.setup_clean_chain = True
        self.num_nodes = 1

    def skip_test_if_missing_module(self):
        self.skip_if_no_wallet()

    def run_test(self):
        self.test_basic_getxpub()

    def test_basic_getxpub(self):
        self.log.info("Test getxpub basics")
        self.nodes[0].createwallet("basic")
        wallet = self.nodes[0].get_wallet_rpc("basic")
        xpub_info = wallet.getxpub()
        assert "xprv" not in xpub_info
        xpub = xpub_info["xpub"]

        xpub_info = wallet.getxpub(True)
        xprv = xpub_info["xprv"]
        assert_equal(xpub_info["xpub"], xpub)

        descs = wallet.listdescriptors(True)
        for desc in descs["descriptors"]:
            if "range" in desc:
                assert xprv in desc["desc"]

        wallet.encryptwallet("pass")
        assert_raises_rpc_error(-13, "Error: Please enter the wallet passphrase with walletpassphrase first", wallet.getxpub, True)
        with WalletUnlock(wallet, "pass"):
            xpub_info = wallet.getxpub(True)
            assert xpub_info["xpub"] != xpub
            assert xpub_info["xprv"] != xprv
            for desc in wallet.listdescriptors(True)["descriptors"]:
                if desc["active"]:
                    assert xpub_info["xprv"] in desc["desc"]
                else:
                    assert xprv in desc["desc"]


if __name__ == '__main__':
    WalletGetXpubTest().main()
