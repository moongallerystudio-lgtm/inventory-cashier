# Inventory Cashier User Guide / 库存收银系统使用指南 / 在庫レジシステム利用ガイド

## 中文

### 1. 打开系统

在 iPad、手机或电脑浏览器中打开云端网址：

`https://inventory-cashier-web.onrender.com`

首页可以进入：

- 库存管理
- 收银结账
- 会员管理
- 销售记录
- 顾客显示屏

页面右上角可切换中文、English、日本語。

### 2. 库存管理

进入“库存管理”页面后，可以录入或修改商品。

填写以下内容：

- 条形码
- 商品名称
- 单价
- 库存数量
- 商品图片

可以手动输入条形码，也可以点击“扫码”使用摄像头扫描。上传图片后，图片会保存到系统中，并在库存页、收银页和顾客显示屏中显示。

如需删除商品，点击商品列表中的“删除”按钮。

### 3. 会员管理

进入“会员管理”页面后，可以新增会员。

填写以下内容：

- 会员番号
- 会员姓名
- 折扣百分比

会员番号可以手动输入，也可以扫码输入。收银时输入会员番号并验证后，系统会自动按会员折扣计算应付金额。

### 4. 收银结账

进入“收银结账”页面。

添加商品方式：

- 扫描商品条形码
- 手动输入条形码后点击“加入”
- 通过商品搜索点选商品

购物车会显示商品、单价、数量、小计和合计金额。可以使用 `+` / `-` 调整数量，也可以移除商品。

如顾客是会员：

1. 输入或扫码会员番号
2. 点击“验证”
3. 系统会显示会员折扣并计算折后价

选择支付方式：

- 现金
- 信用卡
- PayPay
- 微信支付
- 支付宝
- 其他

确认无误后，点击“结账”。结账后系统会自动：

- 记录销售内容
- 记录支付方式
- 扣减库存
- 更新顾客显示屏
- 播放结账完成提示音

### 5. 顾客显示屏

在另一台 iPad 或同一台设备的新标签页打开“顾客显示屏”。

顾客显示屏会显示：

- 商品名称
- 单价
- 数量
- 小计
- 总计

待机时会显示 mooon shop logo。结账完成后，会显示完成动画和感谢语，约 5 秒后回到待机画面。

### 6. 销售记录

进入“销售记录”页面，可以按日期查看当天销售内容。

可查看：

- 销售时间
- 商品明细
- 会员信息
- 支付方式
- 原总价
- 折后价

每天结账结束后，可以下载当天销售记录：

- CSV
- Excel

### 7. iPad 使用建议

建议：

- 使用 Safari 或 Chrome 打开云端网址
- 把网页添加到主屏幕，作为全屏应用使用
- 收银页面和顾客显示屏可分别开在两台 iPad 上
- 保持设备网络稳定

如果页面没有更新，请刷新浏览器页面。如果刚部署新版本，请等待 Render 部署完成后再刷新。

---

## English

### 1. Open The System

Open the cloud URL in a browser on iPad, phone, or computer:

`https://inventory-cashier-web.onrender.com`

From the home page, you can open:

- Inventory
- Cashier
- Members
- Sales Records
- Customer Display

You can switch between Chinese, English, and Japanese from the language buttons.

### 2. Inventory

Open the Inventory page to add or edit products.

Enter:

- Barcode
- Product name
- Price
- Stock quantity
- Product image

You can type the barcode manually or scan it with the camera. Uploaded images are saved in the system and shown in Inventory, Cashier, and Customer Display.

To remove a product, tap the Delete button in the product list.

### 3. Members

Open the Members page to add customers.

Enter:

- Member ID
- Member name
- Discount percentage

The member ID can be typed or scanned. During checkout, enter the member ID and verify it. The system will automatically calculate the discounted payable amount.

### 4. Cashier

Open the Cashier page.

You can add products by:

- Scanning the product barcode
- Typing the barcode and tapping Add
- Searching and tapping a product

The cart shows product name, price, quantity, subtotal, and total. Use `+` / `-` to change quantity, or remove an item.

For members:

1. Enter or scan the member ID
2. Tap Verify
3. The discount will be applied automatically

Select a payment method:

- Cash
- Credit Card
- PayPay
- WeChat Pay
- Alipay
- Other

Tap Checkout after confirming the cart. The system will:

- Save the sale
- Save the payment method
- Reduce stock
- Update the customer display
- Play a checkout completion sound

### 5. Customer Display

Open Customer Display on another iPad or another browser tab.

It shows:

- Product name
- Price
- Quantity
- Subtotal
- Total

When idle, it shows the mooon shop logo. After checkout, it shows a completion animation and thank-you message, then returns to idle after about 5 seconds.

### 6. Sales Records

Open Sales Records to review sales by date.

You can check:

- Sale time
- Item details
- Member information
- Payment method
- Original total
- Payable total

At the end of each day, download the sales records as:

- CSV
- Excel

### 7. iPad Tips

Recommended setup:

- Use Safari or Chrome
- Add the web app to the Home Screen for a full-screen style experience
- Use one iPad for cashier and another iPad for customer display
- Keep the network stable

If the page does not update, refresh the browser. After deployment, wait until Render finishes deploying before refreshing.

---

## 日本語

### 1. システムを開く

iPad、スマートフォン、またはパソコンのブラウザでクラウド URL を開きます。

`https://inventory-cashier-web.onrender.com`

ホーム画面から以下を開けます。

- 在庫管理
- レジ会計
- 会員管理
- 売上記録
- お客様表示

画面の言語ボタンで、中国語、英語、日本語を切り替えできます。

### 2. 在庫管理

在庫管理ページで商品を登録・編集できます。

入力項目：

- バーコード
- 商品名
- 単価
- 在庫数
- 商品画像

バーコードは手入力またはカメラでスキャンできます。アップロードした画像はシステムに保存され、在庫管理、レジ、お客様表示に表示されます。

商品を削除する場合は、商品一覧の「削除」ボタンを押します。

### 3. 会員管理

会員管理ページで会員を登録できます。

入力項目：

- 会員番号
- 会員名
- 割引率

会員番号は手入力またはスキャンできます。レジで会員番号を入力して確認すると、割引後の金額が自動計算されます。

### 4. レジ会計

レジ会計ページを開きます。

商品追加方法：

- 商品バーコードをスキャン
- バーコードを手入力して「追加」
- 商品検索から商品をタップ

カートには商品名、単価、数量、小計、合計が表示されます。`+` / `-` で数量変更、または商品削除ができます。

会員の場合：

1. 会員番号を入力またはスキャン
2. 「確認」を押す
3. 会員割引が自動で適用されます

支払方法を選択します。

- 現金
- クレジットカード
- PayPay
- WeChat Pay
- Alipay
- その他

内容を確認して「会計」を押します。会計後、システムは自動で：

- 売上を記録
- 支払方法を記録
- 在庫を減算
- お客様表示を更新
- 会計完了音を再生

### 5. お客様表示

別の iPad、または別タブで「お客様表示」を開きます。

表示内容：

- 商品名
- 単価
- 数量
- 小計
- 合計

待機中は mooon shop のロゴが表示されます。会計完了後、完了アニメーションと感謝メッセージが表示され、約 5 秒後に待機画面へ戻ります。

### 6. 売上記録

売上記録ページで日付ごとの売上を確認できます。

確認できる内容：

- 売上時間
- 商品明細
- 会員情報
- 支払方法
- 元合計
- 割引後金額

一日の営業終了後、売上記録をダウンロードできます。

- CSV
- Excel

### 7. iPad 利用のおすすめ

おすすめ：

- Safari または Chrome を利用
- ホーム画面に追加してアプリのように利用
- レジ用 iPad とお客様表示用 iPad を分けて使う
- 安定したネットワークで利用

画面が更新されない場合はブラウザを更新してください。新しいバージョンを反映する場合は、Render のデプロイ完了後に更新してください。
