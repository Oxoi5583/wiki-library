# Wiki Library

以分類目錄整理跨媒體作品的私人圖書館。收錄小說、學術書、電影、動畫、遊戲與漫畫的中原文名稱、主創、簡介、作品特色及譯本／發行版本。

館藏以 **Markdown + YAML metadata** 保存，執行根目錄的 `build.py` 即可產生完整靜態網站。網站不需要後端、資料庫、Node.js 或外部 CDN；可以直接開啟，也可以部署到子路徑。

## 快速開始

需要 Python 3.10 或以上版本。

```powershell
python -m pip install -r requirements.txt
python build.py
```

開啟 `site/index.html`。也可以用本機 HTTP 伺服器預覽：

```powershell
python -m http.server 8000 --directory site
```

瀏覽 <http://localhost:8000>；按 `Ctrl+C` 停止伺服器。

預設附有六件**範例館藏**，涵蓋六種媒體。來源連結供查證，狀態與個人筆記僅示範格式。`example: true` 會在列表及條目內顯示提示；新增自己的條目時省略它或設為 `false`。

## 如何分類

三種索引互相獨立：

| 索引 | 回答甚麼 | 例子 |
| --- | --- | --- |
| 媒體 `media` | 它是甚麼形式的作品？ | 小說、學術書、電影、動畫、遊戲 |
| 作品分類 `categories` | 它屬於甚麼文類、作品類型或學術領域？ | 科幻小說、歷史小說、科幻電影、冒險遊戲、社會科學 |
| 標籤 `tags` | 它涉及哪些學科、專業領域或題材？ | 哲學、軍事、政治學、歷史學、人工智慧 |

每件作品只有一個主要媒體，可以有多個作品分類與標籤。分類名稱在 `library.yml` 定義，新增鍵值即可擴充。中文標籤會生成穩定的雜湊網址，頁面仍顯示原標籤。

分類與標籤採用通行名稱，避免「科幻與未來」「認識的邊界」這類自由命名。例如小說可分類為 `science-fiction-novel`（科幻小說），Tag 使用「哲學」「心理學」「認識論」；學術書可分類為 `social-science`（社會科學），Tag 使用「政治學」「歷史學」。沒有館藏的分類放在側欄「其他作品分類」中。

**同一作品的不同譯本／修復版／平台版本**寫在 `editions`；**電影、漫畫、動畫等改編**各建獨立館藏，使用 `related` 連接。例如漫畫《攻殼機動隊》和 1995 年動畫電影應分開記錄。

## 網站介面

- 首頁直接顯示可搜尋的館藏目錄，採逐行列表，取消大標語與封面卡片。
- 每列分為作品／原文標題、媒體／作品分類、作者／主創、內容簡介／作品特色、版本／狀態五欄；標籤、年份、譯者與版本語言也直接顯示。
- 全部館藏：搜尋與媒體、作品分類、標籤、探索狀態的交叉篩選；依收錄日期、名稱或原作年份排序。
- 媒體、作品分類、標籤頁：各自有實際 HTML 頁面，頁內搜尋只比對目前列表。
- 館藏資料：中文譯名、原文標題、其他譯名、主創及角色、內容簡介、作品特色、版本／譯者資料、Markdown 筆記與資料來源。
- 相關作品：優先顯示 `related` 指定的作品，再依共同標籤與分類補上，最多三件，同樣採逐行列表。
- 手機與桌面版、深淺色切換、列印樣式、鍵盤操作及筆記目錄。

搜尋涵蓋**中文譯名、原文標題、別名、創作者與角色、簡介、作品特色、媒體與分類名稱、標籤、系列中原文名稱與別名、版本名稱、譯者、出版社、ISBN 和筆記**。多個關鍵字以空白分隔，採同時符合；不分英文大小寫，也會正規化全形／半形字元。繁簡中文字不會自動互換，需要時可加入 `aliases`。系列也有獨立篩選欄位，條件會保留在網址。

桌面列表的簡介與特色各顯示最多兩行，全文可點作品名稱閱讀。手機仍以每件作品一列排列，欄位會換行，避免橫向捲動。

搜尋及篩選保留在網址裡，可收藏或分享。按 `/` 可跳至搜尋框。搜尋資料直接嵌入 HTML，不依賴 `fetch`，直接開啟本機檔案也能使用。停用 JavaScript 時仍可閱讀所有作品，並經媒體、作品分類與標籤連結瀏覽；即時搜尋和手動深淺色切換需要 JavaScript。

## 目錄結構

```text
wiki-library/
├── build.py
├── library.yml              # 網站名稱、媒體與作品分類
├── requirements.txt
├── data/                    # 全部館藏，唯一資料來源
│   ├── series.yml            # 系列成員與不同順序，非館藏條目
│   ├── novel/solaris/index.md
│   ├── film/stalker/index.md
│   ├── animation/ghost-in-the-shell/index.md
│   ├── game/outer-wilds/index.md
│   ├── academic/imagined-communities/index.md
│   └── comic/pluto/index.md
├── templates/work.md        # 新館藏範本，不參與生成
├── templates/series.yml     # 系列格式範本，不參與生成
├── web/                     # HTML、CSS、JS 與圖示原始檔
├── tests/                   # 建置測試及可選瀏覽器測試
└── site/                    # 生成結果，已被 Git 忽略
```

慣例使用 `data/<媒體>/<英文短名>/index.md`，每個館藏資料夾一份 Markdown。分類以 metadata 為準，資料夾只方便整理；作品網址由 `id` 決定，因此移動資料夾不會改變網站網址。整個 `data/` 會遞迴讀取 Markdown，不要把沒有 metadata 的筆記或範本放進去。補充筆記寫在條目正文。

## 新增一件作品

```powershell
New-Item -ItemType Directory -Force data/novel/my-work
Copy-Item templates/work.md data/novel/my-work/index.md
```

修改 metadata 與正文，再執行 `python build.py`。每件作品的 `id` 必須唯一。

**作品主標題的命名優先順序是：可信中文名 → 英文名 → 原文名。** 新增館藏時要先主動搜尋中文名稱；優先採正式繁體中文名，其次其他正式中文名或有可靠來源的穩定通行中文名。沒有可信中文名才用英文，連英文名也沒有才用原文。不要自行直譯並冒充正式中文譯名。

```yaml
---
id: my-work
title: 中文譯名
original_title: Original Title
aliases: [其他地區譯名]
media: novel
categories: [science-fiction-novel]
tags: [哲學, 心理學]
year: 1961
original_language: 波蘭語
creators:
  - name: 作者名稱
    role: 作者
summary: 一兩句不劇透的內容簡介。
features: 作品的敘事形式、核心議題、研究方法或玩法特徵。
status: curious
added: 2026-10-02
editions:
  - title: 這個譯本的完整名稱
    language: 繁體中文
    format: 紙本
    translators: [譯者名稱]
    publisher: 出版社
    year: 2020
    isbn: ""
    url: https://example.com/book
    notes: 已查證的版本差異。
sources:
  - label: 官方介紹
    url: https://example.com/work
related: []
---
```

上面只示範格式，人物、譯本與網址均為佔位內容。

### Metadata 欄位

| 欄位 | 用途 |
| --- | --- |
| `id` | 必填；小寫英文／數字短名，可用連字號，全館唯一 |
| `title` | 必填；網站主標題。優先可信中文名，其次英文名，最後才用原文名；新增時要先主動查找中文名稱，不猜造官方譯名 |
| `original_title` | 必填；原作實際標題，保留原文字形，與中文譯名同時顯示。中文原作可與 `title` 相同 |
| `aliases` | 其他中文譯名、英文通行名或別名，字串清單；參與搜尋並顯示在詳情頁 |
| `media` | 必填；`library.yml` 定義的媒體鍵值 |
| `categories` | 必填；至少一個已定義的作品分類鍵值，字串清單 |
| `tags` | 學科、專業領域或題材的字串清單，優先使用通行名稱 |
| `year` | 原作年份；未知使用 `""` 或省略，不猜日期 |
| `original_language` | 原作語言；可省略 |
| `creators` | `{name, role}` 清單，角色可為作者、導演、原作、開發、發行等；未知可用 `[]` |
| `summary` | 必填；作品內容簡介，交代背景、情節或研究問題 |
| `features` | 作品特色，描述敘事形式、議題、方法或玩法；可省略，與簡介分開 |
| `status` | 探索狀態，預設 `curious` |
| `added` | 必填；實際收錄日期，`YYYY-MM-DD` |
| `example` | 格式示範標記；自己的館藏預設 `false` |
| `cover` | 同層 `assets/` 裡的圖片相對路徑；省略時自動生成藏書票，不冒充原作封面 |
| `editions` | 譯本、字幕／配音、修復版或平台發行版本的欄位對照表清單；可用 `[]` |
| `sources` | `{label, url}` 清單；網址需要完整 HTTP(S) URL |
| `related` | 其他館藏的 `id` 清單，會檢查是否存在 |

> **YAML 注意：** 單行字串只要包含 ASCII `: `，請把整個值用引號包起來。例如應寫成 `label: "Metal Skin Panic: MADOX-01"`。建置器會對這一種常見漏引號錯誤做保守的記憶體內容錯重試，但不會修改來源檔，也不會放寬重複 key、錯誤型別、壞網址等驗證。\n\n每個 `editions` 項目只有 `title` 必填；其他欄位為 `language`、`format`、`translators`（字串清單）、`publisher`、`year`、`isbn`（字串）、`url` 與 `notes`。**版本年份與原作年份分開保存**。同名作品、不同年份的重拍版本，可在 `title` 或 `aliases` 補充識別資訊。

舊欄位 `interest`（收藏原因）與 `featured` 已停用，不會顯示，也不會自動把主觀收藏原因當成客觀作品特色。新增或更新條目請使用 `features`。

探索狀態：

| 值 | 顯示 |
| --- | --- |
| `curious` | 先收藏 |
| `next` | 想找時間 |
| `in-progress` | 正在探索 |
| `finished` | 已探索 |
| `paused` | 暫時擱著 |

### 圖片與作品連結

圖片或附件放在作品資料夾的 `assets/`，生成時會一起複製：

```markdown
![封面](assets/cover.jpg)

[另一件作品](../../film/stalker/index.md)

[另一件作品的筆記](../../film/stalker/index.md#個人筆記)
```

實際 HTML 的 `.md` 連結會轉成相應館藏網址；參照式連結也支援，程式碼區塊保持原樣。找不到的 Markdown 連結、本機圖片或附件會讓建置失敗；章節錨點本身不驗證。使用二、三級標題會自動產生筆記目錄。

正文支援一般 Markdown、表格、註腳、程式碼區塊與 HTML。這是自己的受信任筆記網站，**不會清理原始 HTML**；不要直接匯入不信任的 HTML。

## 系列與先後關係

系列集中寫在 `data/series.yml`，不需要修改單件作品的 metadata。`templates/series.yml` 提供完整格式示範，預設館藏尚未建立系列。**`media: series` 仍表示「影集」這種媒體，與系列歸屬分開。** 系列本身不增加館藏數，也不合併各部作品的狀態、筆記或譯本。

```yaml
example-cycle:
  title: 範例系列
  original_title: Example Cycle
  aliases: [其他系列名稱]
  description: 說明收錄範圍與各部作品的關係。
  sources: []
  orders:
    - id: release
      title: 出版／發行順序
      notes: 此處說明查證依據、是否完整，以及順序涵蓋的範圍。
      items:
        - work: my-work
          label: 第一部
        - title: 尚未收錄的第二部
          original_title: Example Volume II
          label: 第二部
          notes: 可以保留未收錄作品的位置。
    - id: members
      title: 外傳成員
      ordered: false
      items:
        - work: my-work
```

以上是佔位範例；`work: my-work` 必須替換成已有館藏的 `id`。使用時合併進檔案最外層的對照表，不保留原本的空 `{}`。

- 系列鍵值及各 `orders` 的 `id` 使用小寫英文／數字短名；系列 id 全檔唯一，順序 id 在同一系列內唯一。
- 系列的 `title`、`original_title`、`orders` 必填。每份清單需有 `id`、`title` 和至少一個 `items` 項目；`description`、`aliases`、`sources`、順序的 `notes` 可省略。
- 已收錄項目只填 `work`，名稱自動取自館藏；未收錄項目的 `title` 同樣依「可信中文名 → 英文名 → 原文名」選擇，並另填 `original_title`，不填不存在的 `work`。兩種項目都可加 `label`（正傳、前傳、外傳或卷次）及 `notes`。
- 同一作品可屬於多個系列，也可出現在同系列的多份清單，但同一份清單不能重複同一作品。
- `items` 的排列就是該份清單的順序，不由年份、收錄日期或標題數字推算。出版／發行、故事時間、建議閱讀順序可各建一份清單；支線可另建具名清單。各份清單獨立，不要求收錄相同成員。
- 未知先後或無順序的成員清單用 `ordered: false`，不顯示步驟編號，也不產生前後作品導覽。建議閱讀順序屬於建議，請在 `title`／`notes` 寫清楚推薦者與適用範圍，不冒充官方順序。
- 系列頁顯示所有清單。作品詳情頁標示本作品的位置，分別提供各順序中的前一部／後一部；遇到未收錄作品，顯示名稱與「尚未收錄」，不跳過中間一部、不產生假連結。
- 刪除、移出、合併或更換作品 id 時，同步更新系列引用。只移出館藏而保留系列位置時，把 `work` 改成該作品的 `title`／`original_title`；若移除系列成員，才刪除該項目。懸空引用會使建置失敗。

生成位置為 `site/series/index.html` 與 `site/series/<系列 id>/index.html`；系列名稱會出現在館藏列中，也可用中原文名稱、別名搜尋或透過「全部系列」篩選。系列導覽不依賴 JavaScript。

## 輸出與重建

```powershell
python build.py --output "E:/Websites/wiki-library"
python build.py --source "./my-library" --output "./my-site"
```

預設路徑以 `build.py` 所在位置為準；明確指定的相對路徑以執行指令的目前目錄為準。若使用其他分類設定，可加上 `--config ./another-library.yml`。

| 資料／索引 | 生成位置 |
| --- | --- |
| `id: solaris` | `site/works/solaris/index.html` |
| `media: novel` | `site/media/novel/index.html` |
| 分類 `science-fiction-novel` | `site/categories/science-fiction-novel/index.html` |
| 所有館藏 | `site/catalog/index.html` |
| 標籤索引 | `site/tags/index.html` |
| 作品內 `assets/cover.jpg` | `site/works/<id>/assets/cover.jpg` |

生成的連結都採相對網址與明確的 `index.html`，可以搬移整個 `site/`，或部署在 `/wiki-library/` 子路徑。CSS 直接嵌入每頁；JS 與 favicon 依內容加版本參數。樣式請修改 `web/` 原始檔後重建。

建置會先完成資料、連結與目的路徑檢查，再寫入輸出。`.wiki-library-manifest.json` 記錄管理的檔案，重建不會覆寫同名的非受管理檔案，也不會清空整個輸出資料夾。請保留 manifest，並且每次只執行一個建置程序。

**預設不刪除檔案。** 移走一件館藏後，重建會從索引移除它，但保留舊的生成頁。需要清理時，明確執行：

```powershell
python build.py --prune
```

這只刪除 manifest 記錄且本次不再使用的生成檔案，保留其他檔案與原始 Markdown。多檔案寫入不是整批原子操作；資料夾權限或磁碟問題可能中斷寫入，修正後可再次建置。

## 驗證

```powershell
python -m unittest discover -s tests -v
```

測試涵蓋空館藏、中英標題與搜尋資料、圖片與 Markdown 連結、範例網站的本機連結／錨點、無效 metadata、重複 id、未知媒體及輸出檔案保護。

可選的瀏覽器測試需要 Node.js 和 Playwright；一般建置不需要。自行安裝 `playwright` 後執行 `node tests/browser.cjs`，預設使用本機 Microsoft Edge。可用 `WIKI_BROWSER=chrome` 改用 Chrome，或把 `WIKI_PLAYWRIGHT` 設為已安裝 Playwright 套件的絕對路徑。測試使用 `file://`，驗證搜尋、組合篩選、網址狀態、深淺色、手機版與無 JavaScript 導覽，並輸出已被 Git 忽略的 `preview-*.png` 截圖。


### Build 容錯

Build 會自動正規化可安全判斷的 YAML 顯示值，例如 `label: 1951` 會視為顯示文字 `"1951"`；也會修復常見的 `editions:\n[]`／`sources:\n[]` 斷行，以及未加引號而包含 ASCII `: ` 的文字。這些修復只存在於建置記憶體中，不會放寬 id、work、URL、media、category、related、ordered 等結構性驗證。
