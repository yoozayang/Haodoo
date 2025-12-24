# Haodoo EPUB 下載器

這支腳本會從 Haodoo 站點抓取分類與書籍清單，輸出成 CSV，並可依序慢速下載 EPUB，避免被封鎖。

## 功能
- 取得「大分類 → 書籍 → 書籍頁」完整清單
- 解析作者/書名並寫入 CSV
- 優先下載「直式 epub」，沒有就改用「epub」
- 一次只下載一個檔案，並在每次下載後更新 CSV
- 連線被拒或遭封鎖時，記錄錯誤並停止，方便之後續傳
- 下載檔案依 `~/電子書/<分類>/<作者>/作者 - 書名.epub` 存放

## 安裝依賴
```bash
pip install requests beautifulsoup4
```

## 使用方式
預設同時執行「爬蟲 + 下載」：
```bash
python script/haodoo_epub_downloader.py \
  --start-url "https://www.haodoo.net/?M=hd&P=100" \
  --output haodoo_books.csv \
  --download-dir "~/電子書"
```

只建立清單（不下載）：
```bash
python script/haodoo_epub_downloader.py --crawl --output haodoo_books.csv
```

只下載（用已存在的 CSV 續傳）：
```bash
python script/haodoo_epub_downloader.py --download --output haodoo_books.csv
```

## 參數說明
- `--start-url`：分類首頁，預設 `https://www.haodoo.net/?M=hd`
- `--output`：輸出 CSV 路徑，預設 `haodoo_books.csv`
- `--download-dir`：下載根目錄，預設 `~/電子書`
- `--sleep`：每本下載完成後的等待秒數，預設 `2.0`
- `--timeout`：單一 HTTP 請求逾時秒數，預設 `20`
- `--user-agent`：自訂 User-Agent
- `--max-categories`：爬蟲最多抓取幾個分類（預設 0 = 不限）
- `--max-books`：爬蟲最多抓取幾本書（預設 0 = 不限）
- `--crawl`：只爬清單
- `--download`：只下載（從 CSV 讀取）

## CSV 欄位
欄位依序如下：
```
category,author,title,book_url,download_url,download_name,status,filepath,error
```

欄位說明：
- `category`：分類名稱
- `author`：作者
- `title`：書名
- `book_url`：書籍頁連結
- `download_url`：epub 下載連結
- `download_name`：網站提供的檔名
- `status`：下載狀態（done / blocked / error / no_epub / missing）
- `filepath`：下載後本機路徑
- `error`：錯誤訊息

## 續傳與防封鎖策略
- 下載時會在每本完成後更新 CSV
- 若遇到連線拒絕或 403/429/503 等狀態碼，會標記 `blocked` 並停止
- 重新執行 `--download` 會從尚未完成的項目續傳

## 作者/書名來源
- 以書籍頁內的 `作者《書名》` 標記為準
- 若分類頁未提供作者，會自動從書籍頁補上
