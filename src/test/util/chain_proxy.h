// Copyright (c) 2024-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_CHAIN_PROXY_H
#define BITCOIN_CHAIN_PROXY_H

#include <interfaces/chain.h>

namespace interfaces {
class Handler;

class ChainProxy : public interfaces::Chain
{
    interfaces::Chain* m_chain;

public:
    explicit ChainProxy(Chain* chain) : m_chain(chain) {}

    ~ChainProxy() override {}

    std::optional<int> getHeight() override {
        return m_chain->getHeight();
    }

    uint256 getBlockHash(int height) override {
        return m_chain->getBlockHash(height);
    }

    bool haveBlockOnDisk(int height) override {
        return m_chain->haveBlockOnDisk(height);
    }

    CBlockLocator getTipLocator() override {
        return m_chain->getTipLocator();
    }

    CBlockLocator getActiveChainLocator(const uint256& block_hash) override {
        return m_chain->getActiveChainLocator(block_hash);
    }

    std::optional<int> findLocatorFork(const CBlockLocator& locator) override {
        return m_chain->findLocatorFork(locator);
    }

    bool hasBlockFilterIndex(BlockFilterType filter_type) override {
        return m_chain->hasBlockFilterIndex(filter_type);
    }

    std::optional<bool> blockFilterMatchesAny(BlockFilterType filter_type, const uint256& block_hash,
                                              const GCSFilter::ElementSet& filter_set) override {
        return m_chain->blockFilterMatchesAny(filter_type, block_hash, filter_set);
    }

    bool findBlock(const uint256& hash, const interfaces::FoundBlock& block) override {
        return m_chain->findBlock(hash, block);
    }

    bool findFirstBlockWithTimeAndHeight(int64_t min_time, int min_height, const interfaces::FoundBlock& block) override {
        return m_chain->findFirstBlockWithTimeAndHeight(min_time, min_height, block);
    }

    bool findAncestorByHeight(const uint256& block_hash, int ancestor_height,
                              const interfaces::FoundBlock& ancestor_out) override {
        return m_chain->findAncestorByHeight(block_hash, ancestor_height, ancestor_out);
    }

    bool findAncestorByHash(const uint256& block_hash, const uint256& ancestor_hash,
                            const interfaces::FoundBlock& ancestor_out) override {
        return m_chain->findAncestorByHash(block_hash, ancestor_hash, ancestor_out);
    }

    bool findCommonAncestor(const uint256& block_hash1, const uint256& block_hash2,
                            const interfaces::FoundBlock& ancestor_out, const interfaces::FoundBlock& block1_out,
                            const interfaces::FoundBlock& block2_out) override {
        return m_chain->findCommonAncestor(block_hash1, block_hash2, ancestor_out, block1_out, block2_out);
    }

    void findCoins(std::map<COutPoint, Coin>& coins) override {
        m_chain->findCoins(coins);
    }

    double guessVerificationProgress(const uint256& block_hash) override {
        return m_chain->guessVerificationProgress(block_hash);
    }

    bool hasBlocks(const uint256& block_hash, int min_height, std::optional<int> max_height) override {
        return m_chain->hasBlocks(block_hash, min_height, max_height);
    }

    RBFTransactionState isRBFOptIn(const CTransaction& tx) override {
        return m_chain->isRBFOptIn(tx);
    }

    bool isInMempool(const uint256& txid) override {
        return m_chain->isInMempool(txid);
    }

    bool hasDescendantsInMempool(const uint256& txid) override {
        return m_chain->hasDescendantsInMempool(txid);
    }

    bool broadcastTransaction(const CTransactionRef& tx, const CAmount& max_tx_fee, bool relay,
                              std::string& err_string) override {
        return m_chain->broadcastTransaction(tx, max_tx_fee, relay, err_string);
    }

    void getTransactionAncestry(const uint256& txid, size_t& ancestors, size_t& descendants, size_t* ancestorsize,
                                CAmount* ancestorfees) override {
        m_chain->getTransactionAncestry(txid, ancestors, descendants, ancestorsize, ancestorfees);
    }

    std::map<COutPoint, CAmount>
    calculateIndividualBumpFees(const std::vector<COutPoint>& outpoints, const CFeeRate& target_feerate) override {
        return m_chain->calculateIndividualBumpFees(outpoints, target_feerate);
    }

    std::optional<CAmount>
    calculateCombinedBumpFee(const std::vector<COutPoint>& outpoints, const CFeeRate& target_feerate) override {
        return m_chain->calculateCombinedBumpFee(outpoints, target_feerate);
    }

    void getPackageLimits(unsigned int& limit_ancestor_count, unsigned int& limit_descendant_count) override {
        m_chain->getPackageLimits(limit_ancestor_count, limit_descendant_count);
    }

    util::Result<void> checkChainLimits(const CTransactionRef& tx) override {
        return m_chain->checkChainLimits(tx);
    }

    CFeeRate estimateSmartFee(int num_blocks, bool conservative, FeeCalculation* calc) override {
        return m_chain->estimateSmartFee(num_blocks, conservative, calc);
    }

    unsigned int estimateMaxBlocks() override {
        return m_chain->estimateMaxBlocks();
    }

    CFeeRate mempoolMinFee() override {
        return m_chain->mempoolMinFee();
    }

    CFeeRate relayMinFee() override {
        return m_chain->relayMinFee();
    }

    CFeeRate relayIncrementalFee() override {
        return m_chain->relayIncrementalFee();
    }

    CFeeRate relayDustFee() override {
        return m_chain->relayDustFee();
    }

    bool havePruned() override {
        return m_chain->havePruned();
    }

    bool isReadyToBroadcast() override {
        return m_chain->isReadyToBroadcast();
    }

    bool isInitialBlockDownload() override {
        return m_chain->isInitialBlockDownload();
    }

    bool shutdownRequested() override {
        return m_chain->shutdownRequested();
    }

    void initMessage(const std::string& message) override {
        m_chain->initMessage(message);
    }

    void initWarning(const bilingual_str& message) override {
        m_chain->initWarning(message);
    }

    void initError(const bilingual_str& message) override {
        m_chain->initError(message);
    }

    void showProgress(const std::string& title, int progress, bool resume_possible) override {
        m_chain->showProgress(title, progress, resume_possible);
    }

    std::unique_ptr<Handler> handleNotifications(std::shared_ptr<Notifications> notifications) override {
        return m_chain->handleNotifications(notifications);
    }

    void waitForNotificationsIfTipChanged(const uint256& old_tip) override {

    }

    std::unique_ptr<Handler> handleRpc(const CRPCCommand& command) override {
        return std::unique_ptr<Handler>();
    }

    bool rpcEnableDeprecated(const std::string& method) override {
        return false;
    }

    void rpcRunLater(const std::string& name, std::function<void()> fn, int64_t seconds) override {

    }

    bool rpcSerializationWithoutWitness() override {
        return false;
    }

    common::SettingsValue getSetting(const std::string& arg) override {
        return common::SettingsValue();
    }

    std::vector<common::SettingsValue> getSettingsList(const std::string& arg) override {
        return std::vector<common::SettingsValue>();
    }

    common::SettingsValue getRwSetting(const std::string& name) override {
        return common::SettingsValue();
    }

    bool updateRwSetting(const std::string& name, const common::SettingsValue& value, bool write) override {
        return false;
    }

    void requestMempoolTransactions(Notifications& notifications) override {

    }

    bool hasAssumedValidChain() override {
        return false;
    }

    node::NodeContext* context() override {
        return Chain::context();
    }
};

} // namespace interfaces

#endif // BITCOIN_CHAIN_PROXY_H
