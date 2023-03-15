// Copyright (c) 2011-2022 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_WALLET_COINCONTROL_H
#define BITCOIN_WALLET_COINCONTROL_H

#include <outputtype.h>
#include <policy/feerate.h>
#include <policy/fees.h>
#include <primitives/transaction.h>
#include <script/keyorigin.h>
#include <script/signingprovider.h>
#include <script/standard.h>

#include <optional>
#include <algorithm>
#include <map>
#include <set>

namespace wallet {
const int DEFAULT_MIN_DEPTH = 0;
const int DEFAULT_MAX_DEPTH = 9999999;

//! Default for -avoidpartialspends
static constexpr bool DEFAULT_AVOIDPARTIALSPENDS = false;

class PreselectedInput
{
private:
    //! The previous output being spent by this input
    std::optional<CTxOut> m_txout;
    //! The input weight for spending this input
    std::optional<int64_t> m_weight;
    //! The sequence number for this input
    std::optional<uint32_t> m_sequence;

public:
    void SetTxOut(const CTxOut& txout) { m_txout = txout; }
    CTxOut GetTxOut() const
    {
        assert(m_txout.has_value());
        return m_txout.value();
    }
    bool HasTxOut() const { return m_txout.has_value(); }

    void SetInputWeight(int64_t weight) { m_weight = weight; }
    std::optional<int64_t> GetInputWeight() const
    {
        return m_weight;
    }

    void SetSequence(uint32_t sequence) { m_sequence = sequence; }
    std::optional<uint32_t> GetSequence() const
    {
        return m_sequence;
    }
};

/** Coin Control Features. */
class CCoinControl
{
public:
    //! Custom change destination, if not set an address is generated
    CTxDestination destChange = CNoDestination();
    //! Override the default change type if set, ignored if destChange is set
    std::optional<OutputType> m_change_type;
    //! If false, only safe inputs will be used
    bool m_include_unsafe_inputs = false;
    //! If true, the selection process can add extra unselected inputs from the wallet
    //! while requires all selected inputs be used
    bool m_allow_other_inputs = true;
    //! Includes watch only addresses which are solvable
    bool fAllowWatchOnly = false;
    //! Override automatic min/max checks on fee, m_feerate must be set if true
    bool fOverrideFeeRate = false;
    //! Override the wallet's m_pay_tx_fee if set
    std::optional<CFeeRate> m_feerate;
    //! Override the default confirmation target if set
    std::optional<unsigned int> m_confirm_target;
    //! Override the wallet's m_signal_rbf if set
    std::optional<bool> m_signal_bip125_rbf;
    //! Avoid partial use of funds sent to a given address
    bool m_avoid_partial_spends = DEFAULT_AVOIDPARTIALSPENDS;
    //! Forbids inclusion of dirty (previously used) addresses
    bool m_avoid_address_reuse = false;
    //! Fee estimation mode to control arguments to estimateSmartFee
    FeeEstimateMode m_fee_mode = FeeEstimateMode::UNSET;
    //! Minimum chain depth value for coin availability
    int m_min_depth = DEFAULT_MIN_DEPTH;
    //! Maximum chain depth value for coin availability
    int m_max_depth = DEFAULT_MAX_DEPTH;
    //! SigningProvider that has pubkeys and scripts to do spend size estimation for external inputs
    FlatSigningProvider m_external_provider;
    //! Locktime
    std::optional<uint32_t> m_locktime;

    CCoinControl();

    bool HasSelected() const
    {
        return (m_selected.size() > 0);
    }

    bool IsSelected(const COutPoint& output) const
    {
        return (m_selected.count(output) > 0);
    }

    bool IsExternalSelected(const COutPoint& output) const
    {
        const auto it = m_selected.find(output);
        if (it == m_selected.end()) {
            return false;
        }
        return it->second.HasTxOut();
    }

    bool GetExternalOutput(const COutPoint& outpoint, CTxOut& txout) const
    {
        const auto it = m_selected.find(outpoint);
        if (it == m_selected.end() || !it->second.HasTxOut()) {
            return false;
        }
        txout = it->second.GetTxOut();
        return true;
    }

    PreselectedInput& Select(const COutPoint& output)
    {
        return m_selected[output];
    }

    void UnSelect(const COutPoint& output)
    {
        m_selected.erase(output);
    }

    void UnSelectAll()
    {
        m_selected.clear();
    }

    void ListSelected(std::vector<COutPoint>& vOutpoints) const
    {
        std::transform(m_selected.begin(), m_selected.end(), std::back_inserter(vOutpoints),
                [](const std::map<COutPoint, PreselectedInput>::value_type& pair) {
                    return pair.first;
                });
    }

    void SetInputWeight(const COutPoint& outpoint, int64_t weight)
    {
        m_selected[outpoint].SetInputWeight(weight);
    }

    std::optional<int64_t> GetInputWeight(const COutPoint& outpoint) const
    {
        const auto it = m_selected.find(outpoint);
        if (it == m_selected.end()) {
            return std::nullopt;
        }
        return it->second.GetInputWeight();
    }

    std::optional<uint32_t> GetSequence(const COutPoint& outpoint) const
    {
        const auto it = m_selected.find(outpoint);
        if (it == m_selected.end()) {
            return std::nullopt;
        }
        return it->second.GetSequence();
    }

private:
    std::map<COutPoint, PreselectedInput> m_selected;
};
} // namespace wallet

#endif // BITCOIN_WALLET_COINCONTROL_H
