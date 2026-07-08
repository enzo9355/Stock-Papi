# Papi (papillon) Secret Manager 安全設定指南

在 Google Cloud Secret Manager 中設定或更新金鑰時，如果使用了 `echo "value"` 指令，或者從部分文字編輯器（如 Windows Notepad）直接複製貼上，會自動在金鑰結尾附加 **換行符號（`\n` 或 `\r\n`）**。

這會導致金鑰在使用時（例如 HTTP 標頭的 `Authorization: Bearer <token>` 或 gRPC 通訊）因為包含非法字元而報錯（如 `InvalidHeader`、`Illegal header value`、`Illegal metadata`），進而造成 LINE Bot 發生已讀不回的靜態失敗。

---

## 📌 正確設定金鑰的指令

為了確保金鑰結尾**不包含任何換行符號**，請在 Cloud Shell 或終端機中，統一使用 `printf "%s"`（而非 `echo`）來新增金鑰版本。

### 1. 更新 LINE Channel Access Token
```bash
printf "%s" "YOUR_LINE_CHANNEL_ACCESS_TOKEN_HERE" | \
gcloud secrets versions add stock-papi-line-channel-access-token --data-file=- --project=line-stock-bot-498908
```

### 2. 更新 Gemini API Key
```bash
printf "%s" "YOUR_GEMINI_API_KEY_HERE" | \
gcloud secrets versions add stock-papi-gemini-api-key --data-file=- --project=line-stock-bot-498908
```

### 3. 更新 LINE Channel Secret
```bash
printf "%s" "YOUR_LINE_CHANNEL_SECRET_HERE" | \
gcloud secrets versions add stock-papi-line-channel-secret --data-file=- --project=line-stock-bot-498908
```

### 4. 更新 FinMind 使用者帳號
```bash
printf "%s" "YOUR_FINMIND_USER_HERE" | \
gcloud secrets versions add stock-papi-finmind-user --data-file=- --project=line-stock-bot-498908
```

### 5. 更新 FinMind 密碼
```bash
printf "%s" "YOUR_FINMIND_PASSWORD_HERE" | \
gcloud secrets versions add stock-papi-finmind-password --data-file=- --project=line-stock-bot-498908
```

### 6. 更新提醒排程 Task Token
```bash
printf "%s" "YOUR_ALERT_TASK_TOKEN_HERE" | \
gcloud secrets versions add stock-papi-alert-task-token --data-file=- --project=line-stock-bot-498908
```

---

## 🔍 驗證金鑰是否乾淨

更新金鑰後，若要確認其二進位內容中是否包含換行符號，請執行以下指令來查看十六進位編碼尾端：

```bash
gcloud secrets versions access latest --secret=stock-papi-line-channel-access-token --project=line-stock-bot-498908 | xxd
```

> [!IMPORTANT]
> 乾淨的金鑰尾端**不應該**出現 `0d0a` (即 `\r\n`) 或 `0a` (即 `\n`)。
