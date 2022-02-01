// Copyright (c) 2019-2020 The PIVX developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "qt/pivx/masternodewizarddialog.h"
#include "qt/pivx/forms/ui_masternodewizarddialog.h"

#include "key_io.h"
#include "qt/pivx/mnmodel.h"
#include "qt/pivx/qtutils.h"
#include "qt/walletmodel.h"

#include <QIntValidator>
#include <QRegularExpression>
#include <QGraphicsDropShadowEffect>

static inline QString formatParagraph(const QString& str) {
    return "<p align=\"justify\" style=\"text-align:center;\">" + str + "</p>";
}

static inline QString formatHtmlContent(const QString& str) {
    return "<html><body>" + str + "</body></html>";
}

static void initBtn(std::initializer_list<QPushButton*> args)
{
    QSize BUTTON_SIZE = QSize(22, 22);
    for (QPushButton* btn : args) {
        btn->setMinimumSize(BUTTON_SIZE);
        btn->setMaximumSize(BUTTON_SIZE);
        btn->move(0, 0);
        btn->show();
        btn->raise();
        btn->setVisible(false);
    }
}

static void setCardShadow(QWidget* edit)
{
    QGraphicsDropShadowEffect* shadowEffect = new QGraphicsDropShadowEffect();
    shadowEffect->setColor(QColor(77, 77, 77, 30));
    shadowEffect->setXOffset(0);
    shadowEffect->setYOffset(4);
    shadowEffect->setBlurRadius(6);
    edit->setGraphicsEffect(shadowEffect);
}

MasterNodeWizardDialog::MasterNodeWizardDialog(WalletModel* model, MNModel* _mnModel, QWidget *parent) :
    FocusedDialog(parent),
    ui(new Ui::MasterNodeWizardDialog),
    icConfirm1(new QPushButton(this)),
    icConfirm3(new QPushButton(this)),
    icConfirm4(new QPushButton(this)),
    walletModel(model),
    mnModel(_mnModel)
{
    ui->setupUi(this);

    this->setStyleSheet(parent->styleSheet());
    setCssProperty(ui->frame, "container-dialog");
    ui->frame->setContentsMargins(10,10,10,10);

    setCssProperty({ui->labelLine1, ui->labelLine3}, "line-purple");
    setCssProperty({ui->groupBoxName, ui->groupContainer}, "container-border");
    setCssProperty({ui->pushNumber1, ui->pushNumber3, ui->pushNumber4}, "btn-number-check");
    setCssProperty({ui->pushName1, ui->pushName3, ui->pushName4}, "btn-name-check");

    ui->pushNumber1->setEnabled(false);
    ui->pushNumber3->setEnabled(false);
    ui->pushNumber4->setEnabled(false);
    ui->pushName1->setEnabled(false);
    ui->pushName3->setEnabled(false);
    ui->pushName4->setEnabled(false);

    // Frame 1
    setCssProperty(ui->labelTitle1, "text-title-dialog");
    setCssProperty(ui->labelMessage1a, "text-main-grey");
    setCssProperty(ui->labelMessage1b, "text-main-purple");

    QString collateralAmountStr = GUIUtil::formatBalance(mnModel->getMNCollateralRequiredAmount());
    ui->labelMessage1a->setText(formatHtmlContent(
                formatParagraph(tr("To create a PIVX Masternode you must dedicate %1 (the unit of PIVX) "
                        "to the network (however, these coins are still yours and will never leave your possession).").arg(collateralAmountStr)) +
                formatParagraph(tr("You can deactivate the node and unlock the coins at any time."))));

    // Frame 3
    setCssProperty(ui->labelTitle3, "text-title-dialog");
    setCssProperty(ui->labelMessage3, "text-main-grey");

    ui->labelMessage3->setText(formatHtmlContent(
                formatParagraph(tr("A transaction of %1 will be made").arg(collateralAmountStr)) +
                formatParagraph(tr("to a new empty address in your wallet.")) +
                formatParagraph(tr("The Address is labeled under the master node's name."))));

    initCssEditLine(ui->lineEditName);
    // MN alias must not contain spaces or "#" character
    QRegularExpression rx("^(?:(?![\\#\\s]).)*");
    ui->lineEditName->setValidator(new QRegularExpressionValidator(rx, ui->lineEditName));

    // Frame 3
    setCssProperty(ui->labelTitle4, "text-title-dialog");
    setCssProperty({ui->labelSubtitleIp, ui->labelSubtitlePort}, "text-title");
    setCssSubtitleScreen(ui->labelSubtitleAddressIp);

    initCssEditLine(ui->lineEditIpAddress);
    initCssEditLine(ui->lineEditPort);
    ui->stackedWidget->setCurrentIndex(pos);
    ui->lineEditPort->setEnabled(false);    // use default port number
    if (walletModel->isRegTestNetwork()) {
        ui->lineEditPort->setText("51476");
    } else if (walletModel->isTestNetwork()) {
        ui->lineEditPort->setText("51474");
    } else {
        ui->lineEditPort->setText("51472");
    }

    // Frame 4
    setCssProperty(ui->labelSummary, "text-title-dialog");
    setCssProperty({ui->containerOwner, ui->containerOperator}, "card-governance");
    setCssProperty({ui->labelOwnerSection, ui->labelOperatorSection}, "text-section-title");
    setCssProperty({ui->labelTitleMainAddr, ui->labelTitlePayoutAddr, ui->labelTitleCollateral, ui->labelTitleCollateralIndex,
                    ui->labelTitleOperatorKey, ui->labelTitleOperatorService, ui->labelTitleOperatorPayout, ui->labelTitleOperatorPercentage,
                    ui->labelTitleOperatorService}, "text-title-right");
    setCssProperty({ui->labelMainAddr, ui->labelPayoutAddr, ui->labelCollateralIndex, ui->labelCollateralHash,
                    ui->labelOperatorKey, ui->labelOperatorPayout, ui->labelOperatorPercentage, ui->labelOperatorService}, "text-body2-dialog");
    setCardShadow(ui->containerOwner);
    setCardShadow(ui->containerOperator);

    // Confirm icons
    ui->stackedIcon1->addWidget(icConfirm1);
    ui->stackedIcon3->addWidget(icConfirm3);
    ui->stackedIcon4->addWidget(icConfirm4);
    initBtn({icConfirm1, icConfirm3, icConfirm4});
    setCssProperty({icConfirm1, icConfirm3, icConfirm4}, "ic-step-confirm");

    // Connect btns
    setCssBtnPrimary(ui->btnNext);
    setCssProperty(ui->btnBack , "btn-dialog-cancel");
    ui->btnBack->setVisible(false);
    setCssProperty(ui->pushButtonSkip, "ic-close");

    connect(ui->pushButtonSkip, &QPushButton::clicked, this, &MasterNodeWizardDialog::close);
    connect(ui->btnNext, &QPushButton::clicked, this, &MasterNodeWizardDialog::accept);
    connect(ui->btnBack, &QPushButton::clicked, this, &MasterNodeWizardDialog::onBackClicked);
}

void MasterNodeWizardDialog::showEvent(QShowEvent *event)
{
    if (ui->btnNext) ui->btnNext->setFocus();
}

void MasterNodeWizardDialog::accept()
{
    switch (pos) {
        case 0:{
            ui->stackedWidget->setCurrentIndex(1);
            ui->pushName4->setChecked(false);
            ui->pushName3->setChecked(true);
            ui->pushName1->setChecked(true);
            icConfirm1->setVisible(true);
            ui->pushNumber3->setChecked(true);
            ui->btnBack->setVisible(true);
            ui->lineEditName->setFocus();
            break;
        }
        case 1: {
            // No empty names accepted.
            if (ui->lineEditName->text().isEmpty()) {
                setCssEditLine(ui->lineEditName, false, true);
                return;
            }
            setCssEditLine(ui->lineEditName, true, true);

            ui->stackedWidget->setCurrentIndex(2);
            ui->pushName4->setChecked(false);
            ui->pushName3->setChecked(true);
            ui->pushName1->setChecked(true);
            icConfirm3->setVisible(true);
            ui->pushNumber4->setChecked(true);
            ui->lineEditIpAddress->setFocus();
            break;
        }
        case 2: {
            // No empty address accepted
            if (ui->lineEditIpAddress->text().isEmpty()) {
                return;
            }
            icConfirm4->setVisible(true);
            isOk = createMN();
            if (!isOk) {
                inform(returnStr);
                return;
            }
            if (!mnSummary) QDialog::accept();
            ui->pushName4->setChecked(true);
        }
        case 3: {
            ui->btnBack->setVisible(false);
            ui->btnNext->setText("CLOSE");
            ui->stackedWidget->setCurrentIndex(3);
            setSummary();
            break;
        }
        case 4: {
            QDialog::accept();
        }
    }
    pos++;
}

static void setShortText(QLabel* label, const QString& str, int size)
{
    label->setText(str.left(size) + "..." + str.right(size));
}

void MasterNodeWizardDialog::setSummary()
{
    assert(mnSummary);
    setShortText(ui->labelMainAddr, QString::fromStdString(mnSummary->ownerAddr), 14);
    setShortText(ui->labelPayoutAddr, QString::fromStdString(mnSummary->ownerPayoutAddr), 14);
    setShortText(ui->labelCollateralHash, QString::fromStdString(mnSummary->collateralOut.hash.GetHex()), 20);
    ui->labelCollateralIndex->setText(QString::number(mnSummary->collateralOut.n));
    ui->labelOperatorService->setText(QString::fromStdString(mnSummary->service));
    ui->labelOperatorKey->setText(QString::fromStdString(mnSummary->operatorKey));
}

bool MasterNodeWizardDialog::createMN()
{
    if (!walletModel) {
        returnStr = tr("walletModel not set");
        return false;
    }

    // validate IP address
    QString addressLabel = ui->lineEditName->text();
    if (addressLabel.isEmpty()) {
        returnStr = tr("address label cannot be empty");
        return false;
    }

    QString addressStr = ui->lineEditIpAddress->text();
    QString portStr = ui->lineEditPort->text();
    if (addressStr.isEmpty() || portStr.isEmpty()) {
        returnStr = tr("IP or port cannot be empty");
        return false;
    }
    if (!MNModel::validateMNIP(addressStr)) {
        returnStr = tr("Invalid IP address");
        return false;
    }

    std::string alias = addressLabel.toStdString();
    std::string ipAddress = addressStr.toStdString();
    std::string port = portStr.toStdString();

    // Look for a valid collateral utxo
    COutPoint collateralOut;

    // If not found create a new collateral tx
    if (!walletModel->getMNCollateralCandidate(collateralOut)) {
        // New receive address
        auto r = walletModel->getNewAddress(alias);
        if (!r) return errorOut(tr(r.getError().c_str()));
        if (!mnModel->createMNCollateral(addressLabel,
                                         QString::fromStdString(r.getObjResult()->ToString()),
                                         collateralOut,
                                         returnStr)) {
            // error str set internally
            return false;
        }
    }

    if (walletModel->isV6Enforced()) {
        // Deterministic

        // For now, create every single key inside the wallet
        // later this can be customized by the user.

        // Create owner addr
        const auto ownerAddr = walletModel->getNewAddress("dmn_owner_" + alias);
        if (!ownerAddr) return errorOut(tr(ownerAddr.getError().c_str()));
        const CKeyID* ownerKeyId = ownerAddr.getObjResult()->getKeyID();

        // Create payout addr
        const auto payoutAddr = walletModel->getNewAddress("dmn_payout_" + alias);
        if (!payoutAddr) return errorOut(tr(payoutAddr.getError().c_str()));
        const std::string& payoutStr{payoutAddr.getObjResult()->ToString()};

        // For now, collateral key is always inside the wallet
        std::string error_str;
        bool res = mnModel->createDMN(alias,
                                      collateralOut,
                                      ipAddress,
                                      port,
                                      ownerKeyId,
                                      nullopt, // generate operator key
                                      nullopt, // use owner key as voting key
                                      {payoutStr}, // use owner key as payout script
                                      error_str,
                                      nullopt, // operator percentage
                                      nullopt); // operator payout script
        if (!res) {
            return errorOut(tr(error_str.c_str()));
        }

        std::string ownerAddrStr = ownerAddr.getObjResult()->ToString();
        mnSummary = std::make_unique<MNSummary>(alias,
                                                ipAddress+":"+port,
                                                collateralOut,
                                                ownerAddrStr,
                                                payoutAddr.getObjResult()->ToString(),
                                                "fa3b23b341ccba23ab398befea2321bc46f", // todo: add real operator key..
                                                ownerAddrStr, // voting key, for now fixed to owner addr
                                                0, // operator percentage
                                                nullopt); // operator payout

        returnStr = tr("Deterministic Masternode created! It will appear on your list on the next mined block!");
    } else {
        // Legacy
        CKey secret;
        secret.MakeNewKey(false);
        std::string mnKeyString = KeyIO::EncodeSecret(secret);
        std::string mnPubKeyStr = secret.GetPubKey().GetHash().GetHex();

        mnEntry = mnModel->createLegacyMN(collateralOut, alias, ipAddress, port, mnKeyString, mnPubKeyStr, returnStr);
        if (!mnEntry) return false;
        // Update list
        mnModel->addMn(mnEntry);
        returnStr = tr("Masternode created! Wait %1 confirmations before starting it.").arg(mnModel->getMasternodeCollateralMinConf());
    }
    return true;
}

void MasterNodeWizardDialog::onBackClicked()
{
    if (pos == 0) return;
    pos--;
    switch(pos) {
        case 0:{
            ui->stackedWidget->setCurrentIndex(0);
            ui->btnNext->setFocus();
            ui->pushNumber1->setChecked(true);
            ui->pushNumber4->setChecked(false);
            ui->pushNumber3->setChecked(false);
            ui->pushName4->setChecked(false);
            ui->pushName3->setChecked(false);
            ui->pushName1->setChecked(true);
            icConfirm1->setVisible(false);
            ui->btnBack->setVisible(false);
            break;
        }
        case 1: {
            ui->stackedWidget->setCurrentIndex(1);
            ui->lineEditName->setFocus();
            ui->pushNumber4->setChecked(false);
            ui->pushNumber3->setChecked(true);
            ui->pushName4->setChecked(false);
            ui->pushName3->setChecked(true);
            icConfirm3->setVisible(false);

            break;
        }
    }
}

void MasterNodeWizardDialog::inform(const QString& text)
{
    if (!snackBar)
        snackBar = new SnackBar(nullptr, this);
    snackBar->setText(text);
    snackBar->resize(this->width(), snackBar->height());
    openDialog(snackBar, this);
}

bool MasterNodeWizardDialog::errorOut(const QString& err)
{
    returnStr = err;
    return false;
}

MasterNodeWizardDialog::~MasterNodeWizardDialog()
{
    delete snackBar;
    delete ui;
}
