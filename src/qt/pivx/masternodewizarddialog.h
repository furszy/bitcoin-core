// Copyright (c) 2019 The PIVX developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef MASTERNODEWIZARDDIALOG_H
#define MASTERNODEWIZARDDIALOG_H

#include "qt/pivx/focuseddialog.h"
#include "qt/pivx/snackbar.h"
#include "masternodeconfig.h"
#include "qt/pivx/pwidget.h"

class MNModel;
class WalletModel;

namespace Ui {
class MasterNodeWizardDialog;
class QPushButton;
}

struct MNSummary
{
    MNSummary(const std::string& _alias, const std::string& _service, const COutPoint& _collateralOut,
              const std::string& _ownerAddr, const std::string& _ownerPayoutAddr, const std::string& _operatorKey,
              const std::string& _votingKey, int _operatorPercentage,
              const Optional<std::string>& _operatorPayoutAddr) : alias(_alias), service(_service),
                                                            collateralOut(_collateralOut),
                                                            ownerAddr(_ownerAddr),
                                                            ownerPayoutAddr(_ownerPayoutAddr),
                                                            operatorKey(_operatorKey), votingKey(_votingKey),
                                                            operatorPercentage(_operatorPercentage),
                                                            operatorPayoutAddr(_operatorPayoutAddr) {}

    std::string alias;
    std::string service;
    COutPoint collateralOut;
    std::string ownerAddr;
    std::string ownerPayoutAddr;
    std::string operatorKey;
    std::string votingKey;
    int operatorPercentage{0};
    Optional<std::string> operatorPayoutAddr;
};

class MasterNodeWizardDialog : public FocusedDialog, public PWidget::Translator
{
    Q_OBJECT

public:
    explicit MasterNodeWizardDialog(WalletModel* walletMode,
                                    MNModel* mnModel,
                                    QWidget *parent = nullptr);
    ~MasterNodeWizardDialog() override;
    void showEvent(QShowEvent *event) override;
    QString translate(const char *msg) override { return tr(msg); }

    QString returnStr = "";
    bool isOk = false;
    CMasternodeConfig::CMasternodeEntry* mnEntry = nullptr;

private Q_SLOTS:
    void accept() override;
    void onBackClicked();
private:
    Ui::MasterNodeWizardDialog *ui;
    QList<QPushButton*> list_icConfirm{};
    QList<QPushButton*> list_pushNumber{};
    QList<QPushButton*> list_pushName{};
    SnackBar* snackBar{nullptr};
    int pos = 0;
    std::unique_ptr<MNSummary> mnSummary{nullptr};
    bool isDeterministic{false};

    WalletModel* walletModel{nullptr};
    MNModel* mnModel{nullptr};
    bool createMN();
    void setSummary();
    void inform(const QString& text);
    bool errorOut(const QString& err);

    void moveToNextPage(int currentPos, int nextPos);
    void moveBack(int backPos);
};

#endif // MASTERNODEWIZARDDIALOG_H
