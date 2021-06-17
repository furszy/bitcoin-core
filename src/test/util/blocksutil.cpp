// Copyright (c) 2021 The PIVX developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#include "test/util/blocksutil.h"
#include "validation.h"
#include "validationinterface.h"

#include <boost/test/unit_test.hpp>

class BlockStateCatcher : public CValidationInterface
{
public:
    uint256 hash;
    bool found;
    CValidationState state;

    BlockStateCatcher(const uint256& hashIn) : hash(hashIn), found(false), state(){};

protected:
    virtual void BlockChecked(const CBlock& block, const CValidationState& stateIn)
    {
        if (block.GetHash() != hash) return;
        found = true;
        state = stateIn;
    };
};

void ProcessBlockAndCheckRejectionReason(std::shared_ptr<CBlock>& pblock,
                                         const std::string& blockRejectionReason,
                                         int expectedChainHeight)
{
    CValidationState state;
    BlockStateCatcher stateChecker(pblock->GetHash());
    RegisterValidationInterface(&stateChecker);
    ProcessNewBlock(state, pblock, nullptr);
    UnregisterValidationInterface(&stateChecker);
    BOOST_CHECK(stateChecker.found);
    state = stateChecker.state;
    BOOST_CHECK_EQUAL(WITH_LOCK(cs_main, return chainActive.Height();), expectedChainHeight);
    BOOST_CHECK(!state.IsValid());
    BOOST_CHECK_EQUAL(state.GetRejectReason(), blockRejectionReason);
}
