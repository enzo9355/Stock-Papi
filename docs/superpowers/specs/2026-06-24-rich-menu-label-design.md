# 圖文選單標籤與設計稿更新設計

## 目標

更新 LINE 圖文選單的 repo 交付物，讓文字更大、更清楚，並移除左下角 `AI Quant Bot` 字樣。同時把原本選單中的「強勢訊號」欄位改成「產業預測」，點擊後送出 `預測`，讓使用者進入產業預測流程。

## 現況

- repo 內沒有實際 Rich Menu 圖檔。
- repo 內沒有 Rich Menu API 建立腳本。
- `docs/line-to-web-map.md` 說明實際 Rich Menu 由 LINE Official Account Manager 手動設定。
- `app.py` 的 `build_line_navigation_flex()` 是 Rich Menu 的 LINE 內預覽版本。

## 新設計

六格選單維持不變，但第三格改名：

| 位置 | 顯示文字 | 動作 |
| --- | --- | --- |
| 左上 | 今日盤勢 | 傳送 `今日盤勢` |
| 中上 | 我的關注 | 傳送 `我的關注` |
| 右上 | 產業預測 | 傳送 `預測` |
| 左下 | 提醒管理 | 傳送 `提醒管理` |
| 中下 | 投資試算 | 傳送 `投資試算` |
| 右下 | 完整分析 | 傳送 `完整分析` |

原本 `強勢訊號` 指令保留，不刪除；它仍代表「關注清單內的強勢股票」。只是圖文選單不再把它當主要入口。

## 視覺規則

- 新增 `assets/rich-menu.svg` 作為可版本控管的設計稿來源檔。
- 文字放大到適合手機閱讀。
- 左下角不放 `AI Quant Bot` 或任何品牌小字。
- 保持深色底、綠色重點色、六格清楚分隔。
- 不新增圖片處理依賴；SVG 可由瀏覽器或設計工具匯出 PNG 後上傳 LINE 後台。

## 測試

- `build_line_navigation_flex()` 需包含 `產業預測`。
- `build_line_navigation_flex()` 不再包含 `強勢訊號`。
- `產業預測` 的 action text 必須是 `預測`。
- `docs/line-to-web-map.md` 需反映第三格為產業預測。

## 不做的事

- 不新增 Rich Menu API 上傳腳本。
- 不直接修改 LINE 官方後台。
- 不新增外部套件。
