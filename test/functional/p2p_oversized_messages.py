#!/usr/bin/env python3
# Copyright (c) The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test that P2P messages too large to be processed are dropped before
deserialization.

Some messages can be rejected on their size alone, before the node spends work
deserializing them. This file groups those cases by message type.

tx: a standard transaction's weight is at least its serialized size, so a tx
message larger than MAX_STANDARD_TX_WEIGHT can never be a transaction the node
would accept while enforcing standardness. The node drops such a message without
deserializing it, computing its wtxid from the raw bytes only to forget any
outstanding request, so other announcing peers are not fallen back to."""

import time

from test_framework.messages import (
    CInv,
    COutPoint,
    CTransaction,
    CTxIn,
    CTxInWitness,
    CTxOut,
    MSG_TX,
    MSG_TYPE_MASK,
    MSG_WTX,
    msg_inv,
    msg_tx,
)
from test_framework.p2p import (
    GETDATA_TX_INTERVAL,
    P2PInterface,
)
from test_framework.script import CScript, OP_TRUE
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal
from test_framework.wallet import MiniWallet

MAX_STANDARD_TX_WEIGHT = 400_000


def tx_of_serialized_size(target_size):
    """A transaction whose serialized size (with witness) is about target_size,
    padded with 1-byte witness stack items."""
    tx = CTransaction()
    tx.vin = [CTxIn(COutPoint(0, 0xffffffff))]
    tx.vout = [CTxOut(0, CScript([OP_TRUE]))]
    tx.wit.vtxinwit = [CTxInWitness()]
    base = len(tx.serialize_with_witness())
    # Each 1-byte item costs 2 bytes on the wire (1 size byte + 1 data byte).
    n_items = max(0, (target_size - base) // 2)
    tx.wit.vtxinwit[0].scriptWitness.stack = [b"\x01"] * n_items
    return tx


class TxGetdataCounter(P2PInterface):
    """A wtxid-relay peer that counts the tx getdata requests the node sends it."""
    def __init__(self):
        super().__init__(wtxidrelay=True)
        self.tx_getdata_count = 0

    def on_getdata(self, message):
        for i in message.inv:
            if i.type & MSG_TYPE_MASK in (MSG_TX, MSG_WTX):
                self.tx_getdata_count += 1


class OversizedMessagesTest(BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 1

    def run_test(self):
        self.wallet = MiniWallet(self.nodes[0])
        self.generate(self.wallet, 1)  # leave IBD so tx messages are processed
        # Oversized tx messages.
        self.test_unrequested_oversized_dropped()
        self.test_within_limit_still_processed()
        self.test_oversized_forgotten_no_fallback()
        self.test_disabled_without_require_standard()

    def test_unrequested_oversized_dropped(self):
        self.log.info("An unrequested oversized tx message is dropped before deserialization")
        node = self.nodes[0]
        peer = node.add_p2p_connection(P2PInterface())
        oversized = tx_of_serialized_size(MAX_STANDARD_TX_WEIGHT + 1000)
        assert len(oversized.serialize_with_witness()) > MAX_STANDARD_TX_WEIGHT
        with node.assert_debug_log(["oversized tx message"]):
            peer.send_and_ping(msg_tx(oversized))
        assert peer.is_connected  # not disconnected
        assert_equal(node.getmempoolinfo()["size"], 0)
        node.disconnect_p2ps()

    def test_within_limit_still_processed(self):
        self.log.info("A tx message within the size limit is still deserialized (and rejected on its merits)")
        node = self.nodes[0]
        peer = node.add_p2p_connection(P2PInterface())
        within_limit = tx_of_serialized_size(MAX_STANDARD_TX_WEIGHT - 1000)
        assert len(within_limit.serialize_with_witness()) <= MAX_STANDARD_TX_WEIGHT
        # "was not accepted" is only logged after the tx has been deserialized.
        with node.assert_debug_log(["was not accepted"], unexpected_msgs=["oversized tx message"]):
            peer.send_and_ping(msg_tx(within_limit))
        assert_equal(node.getmempoolinfo()["size"], 0)
        node.disconnect_p2ps()

    def test_oversized_forgotten_no_fallback(self):
        self.log.info("Dropping an oversized tx forgets the request, so other announcers are not fallen back to")
        node = self.nodes[0]
        oversized = tx_of_serialized_size(MAX_STANDARD_TX_WEIGHT + 1000)
        wtxid = oversized.wtxid_int
        peer1 = node.add_p2p_connection(TxGetdataCounter())
        peer2 = node.add_p2p_connection(TxGetdataCounter())
        for p in [peer1, peer2]:
            p.send_without_ping(msg_inv([CInv(MSG_WTX, wtxid)]))
        # The node asks one of the two announcers for the transaction.
        peer2.wait_until(lambda: sum(p.tx_getdata_count for p in [peer1, peer2]) == 1)
        asked, other = (peer1, peer2) if peer1.tx_getdata_count == 1 else (peer2, peer1)
        assert_equal(other.tx_getdata_count, 0)
        # It responds with the oversized tx: dropped, and the request forgotten.
        with node.assert_debug_log(["oversized tx message"]):
            asked.send_and_ping(msg_tx(oversized))
        # Jump past the request's expiry. Without forgetting, the node would now
        # fall back to the other announcer; it must not.
        node.setmocktime(int(time.time()) + GETDATA_TX_INTERVAL + 1)
        other.sync_with_ping()
        assert_equal(other.tx_getdata_count, 0)
        node.disconnect_p2ps()
        node.setmocktime(0)

    def test_disabled_without_require_standard(self):
        self.log.info("With -acceptnonstdtxn the cap is disabled and the oversized tx is deserialized")
        self.restart_node(0, extra_args=["-acceptnonstdtxn=1"])
        self.wallet = MiniWallet(self.nodes[0])
        self.generate(self.wallet, 1)
        node = self.nodes[0]
        peer = node.add_p2p_connection(P2PInterface())
        oversized = tx_of_serialized_size(MAX_STANDARD_TX_WEIGHT + 1000)
        with node.assert_debug_log(["was not accepted"], unexpected_msgs=["oversized tx message"]):
            peer.send_and_ping(msg_tx(oversized))


if __name__ == '__main__':
    OversizedMessagesTest(__file__).main()
