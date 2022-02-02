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

static void initTopBtns(const QList<QPushButton*>& icons, const QList<QPushButton*>& numbers, const QList<QPushButton*>& names)
{
    assert(icons.size() == names.size() && names.size() == numbers.size());
    QSize BUTTON_SIZE = QSize(22, 22);
    for (int i=0; i < icons.size(); i++) {
        auto pushNumber = numbers[i];
        auto pushIcon = icons[i];
        auto pushName = names[i];

        setCssProperty(pushNumber, "btn-number-check");
        pushNumber->setEnabled(false);

        setCssProperty(pushName, "btn-name-check");
        pushName->setEnabled(false);

        setCssProperty(pushIcon, "ic-step-confirm");
        pushIcon->setMinimumSize(BUTTON_SIZE);
        pushIcon->setMaximumSize(BUTTON_SIZE);
        pushIcon->move(0, 0);
        pushIcon->show();
        pushIcon->raise();
        pushIcon->setVisible(false);
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
    walletModel(model),
    mnModel(_mnModel)
{
    ui->setupUi(this);
    setStyleSheet(parent->styleSheet());
    setCssProperty(ui->frame, "container-dialog");
    ui->frame->setContentsMargins(10,10,10,10);

    isDeterministic = walletModel->isV6Enforced();

    for (int i = 0; i < 5; i++) list_icConfirm.push_back(new QPushButton(this));
    list_pushNumber = {ui->pushNumber1, ui->pushNumber2, ui->pushNumber3, ui->pushNumber4, ui->pushNumber5};
    list_pushName = {ui->pushName1, ui->pushName2, ui->pushName3, ui->pushName4, ui->pushName5};
    setCssProperty({ui->labelLine1, ui->labelLine2, ui->labelLine3, ui->labelLine4}, "line-purple");
    setCssProperty({ui->groupBoxName, ui->groupContainer}, "container-border");

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
    ui->stackedIcon1->addWidget(list_icConfirm[0]);
    ui->stackedIcon2->addWidget(list_icConfirm[1]);
    ui->stackedIcon3->addWidget(list_icConfirm[2]);
    ui->stackedIcon4->addWidget(list_icConfirm[3]);
    ui->stackedIcon5->addWidget(list_icConfirm[4]);
    initTopBtns(list_icConfirm, list_pushNumber, list_pushName);

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

void setBtnsChecked(QList<QPushButton*> btns, int start, int end)
{
    for (int i=start; i < btns.size(); i++) {
        btns[i]->setChecked(i <= end);
    }
}

void MasterNodeWizardDialog::moveToNextPage(int currentPos, int nextPos)
{
    ui->stackedWidget->setCurrentIndex(nextPos);
    list_icConfirm[currentPos]->setVisible(true);
    list_pushNumber[nextPos]->setChecked(true);
    setBtnsChecked(list_pushName, pos, nextPos);
}

void MasterNodeWizardDialog::accept()
{
    int nextPos = pos + 1;
    switch (pos) {
        case 0: {
            moveToNextPage(pos, nextPos);
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
            moveToNextPage(pos, nextPos);
            ui->lineEditIpAddress->setFocus();
            break;
        }
        case 2: {
            // No empty address accepted
            if (ui->lineEditIpAddress->text().isEmpty()) {
                return;
            }
            if (!isDeterministic) {
                isOk = createMN();
                QDialog::accept();
            } else {
                moveToNextPage(pos, nextPos);
            }
            break;
        }
        case 3: {
            // todo: add owner page
            moveToNextPage(pos, nextPos);
            break;
        }
        case 4: {
            // todo: add operator page
            moveToNextPage(pos, nextPos);
            break;
        }
        case 5: {
            ui->btnBack->setVisible(false);
            ui->btnNext->setText("CLOSE");
            ui->stackedWidget->setCurrentIndex(3);
            setSummary();
            break;
        }
        case 6: {
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

    if (isDeterministic) {
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

void MasterNodeWizardDialog::moveBack(int backPos)
{
    ui->stackedWidget->setCurrentIndex(backPos);
    list_icConfirm[pos]->setVisible(false);
    setBtnsChecked(list_pushName, backPos, backPos);
    setBtnsChecked(list_pushNumber, backPos, backPos);
}

void MasterNodeWizardDialog::onBackClicked()
{
    if (pos == 0) return;
    pos--;
    moveBack(pos);
    switch (pos) {
        case 0:{
            ui->btnBack->setVisible(false);
            ui->btnNext->setFocus();
            break;
        }
        case 1: {
            ui->lineEditName->setFocus();
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
