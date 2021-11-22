#!/usr/bin/env bash
#
# Copyright (c) 2018-2021 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
#
# Check for circular dependencies

export LC_ALL=C

EXPECTED_CIRCULAR_DEPENDENCIES=(
    "activemasternode -> masternode-sync -> activemasternode"
    "activemasternode -> masternodeman -> activemasternode"
    "budget/budgetmanager -> masternode-sync -> budget/budgetmanager"
    "budget/budgetmanager -> net_processing -> budget/budgetmanager"
    "budget/budgetmanager -> validation -> budget/budgetmanager"
    "budget/budgetmanager -> wallet/wallet -> budget/budgetmanager"
    "chain -> legacy/stakemodifier -> chain"
    "chainparams -> checkpoints -> chainparams"
    "chainparamsbase -> util/system -> chainparamsbase"
    "consensus/params -> consensus/upgrades -> consensus/params"
    "crypter -> wallet/wallet -> crypter"
    "evo/deterministicmns -> masternodeman -> evo/deterministicmns"
    "kernel -> validation -> kernel"
    "masternode -> masternode-sync -> masternode"
    "masternode -> masternodeman -> masternode"
    "masternode -> wallet/wallet -> masternode"
    "masternode-payments -> masternode-sync -> masternode-payments"
    "masternode-payments -> masternodeman -> masternode-payments"
    "masternode-payments -> net_processing -> masternode-payments"
    "masternode-payments -> validation -> masternode-payments"
    "masternode-sync -> masternodeman -> masternode-sync"
    "masternode-sync -> validation -> masternode-sync"
    "masternodeman -> net_processing -> masternodeman"
    "masternodeman -> validation -> masternodeman"
    "policy/fees -> txmempool -> policy/fees"
    "policy/policy -> validation -> policy/policy"
    "qt/pivx/addresseswidget -> qt/pivx/pivxgui -> qt/pivx/addresseswidget"
    "qt/pivx/navmenuwidget -> qt/pivx/pivxgui -> qt/pivx/navmenuwidget"
    "qt/pivx/pivxgui -> qt/pivx/qtutils -> qt/pivx/pivxgui"
    "qt/pivx/qtutils -> qt/pivx/snackbar -> qt/pivx/qtutils"
    "sapling/saplingscriptpubkeyman -> wallet/wallet -> sapling/saplingscriptpubkeyman"
    "spork -> sporkdb -> spork"
    "spork -> validation -> spork"
    "txmempool -> validation -> txmempool"
    "validation -> validationinterface -> validation"
    "validation -> zpiv/zpivmodule -> validation"
    "wallet/fees -> wallet/wallet -> wallet/fees"
    "wallet/scriptpubkeyman -> wallet/wallet -> wallet/scriptpubkeyman"
    "wallet/wallet -> wallet/walletdb -> wallet/wallet"
    "wallet/wallet -> zpivchain -> wallet/wallet"
    "zpiv/zpivmodule -> zpivchain -> zpiv/zpivmodule"
    "chain -> chainparams -> checkpoints -> chain"
    "chain -> legacy/stakemodifier -> stakeinput -> chain"
    "chain -> legacy/stakemodifier -> validation -> chain"
    "chainparamsbase -> util/system -> logging -> chainparamsbase"
    "consensus/zerocoin_verify -> spork -> validation -> consensus/zerocoin_verify"
    "evo/deterministicmns -> masternode -> masternode-sync -> evo/deterministicmns"
    "evo/deterministicmns -> masternodeman -> net_processing -> evo/deterministicmns"
    "evo/deterministicmns -> masternode -> wallet/wallet -> evo/deterministicmns"
    "kernel -> stakeinput -> wallet/wallet -> kernel"
    "legacy/validation_zerocoin_legacy -> wallet/wallet -> validation -> legacy/validation_zerocoin_legacy"
    "masternode-sync -> masternodeman -> net_processing -> masternode-sync"
    "primitives/transaction -> script/standard -> script/interpreter -> primitives/transaction"
    "qt/askpassphrasedialog -> qt/pivx/pivxgui -> qt/pivx/topbar -> qt/askpassphrasedialog"
    "qt/pivx/coldstakingwidget -> qt/pivx/tooltipmenu -> qt/pivx/pivxgui -> qt/pivx/coldstakingwidget"
    "qt/pivx/masternodeswidget -> qt/pivx/tooltipmenu -> qt/pivx/pivxgui -> qt/pivx/masternodeswidget"
    "qt/pivx/pivxgui -> qt/pivx/send -> qt/pivx/tooltipmenu -> qt/pivx/pivxgui"
    "chain -> legacy/stakemodifier -> validation -> evo/specialtx_validation -> chain"
    "chain -> legacy/stakemodifier -> validation -> validationinterface -> chain"
    "chain -> legacy/stakemodifier -> stakeinput -> txdb -> chain"
    "chain -> legacy/stakemodifier -> validation -> undo -> chain"
    "chain -> legacy/stakemodifier -> validation -> pow -> chain"
    "chain -> legacy/stakemodifier -> validation -> zpivchain -> chain"
    "consensus/tx_verify -> consensus/zerocoin_verify -> spork -> validation -> consensus/tx_verify"
    "evo/deterministicmns -> masternodeman -> net_processing -> validationinterface -> evo/deterministicmns"
    "evo/deterministicmns -> masternodeman -> validation -> evo/specialtx_validation -> evo/deterministicmns"
    "chain -> legacy/stakemodifier -> stakeinput -> wallet/wallet -> spork -> net_processing -> chain"
)

EXIT_CODE=0

CIRCULAR_DEPENDENCIES=()

IFS=$'\n'
for CIRC in $(cd src && ../contrib/devtools/circular-dependencies.py {*,*/*,*/*/*}.{h,cpp} | sed -e 's/^Circular dependency: //'); do
    CIRCULAR_DEPENDENCIES+=( "$CIRC" )
    IS_EXPECTED_CIRC=0
    for EXPECTED_CIRC in "${EXPECTED_CIRCULAR_DEPENDENCIES[@]}"; do
        if [[ "${CIRC}" == "${EXPECTED_CIRC}" ]]; then
            IS_EXPECTED_CIRC=1
            break
        fi
    done
    if [[ ${IS_EXPECTED_CIRC} == 0 ]]; then
        echo "A new circular dependency in the form of \"${CIRC}\" appears to have been introduced."
        echo
        EXIT_CODE=1
    fi
done

for EXPECTED_CIRC in "${EXPECTED_CIRCULAR_DEPENDENCIES[@]}"; do
    IS_PRESENT_EXPECTED_CIRC=0
    for CIRC in "${CIRCULAR_DEPENDENCIES[@]}"; do
        if [[ "${CIRC}" == "${EXPECTED_CIRC}" ]]; then
            IS_PRESENT_EXPECTED_CIRC=1
            break
        fi
    done
    if [[ ${IS_PRESENT_EXPECTED_CIRC} == 0 ]]; then
        echo "Good job! The circular dependency \"${EXPECTED_CIRC}\" is no longer present."
        echo "Please remove it from EXPECTED_CIRCULAR_DEPENDENCIES in $0"
        echo "to make sure this circular dependency is not accidentally reintroduced."
        echo
        EXIT_CODE=1
    fi
done

exit ${EXIT_CODE}
