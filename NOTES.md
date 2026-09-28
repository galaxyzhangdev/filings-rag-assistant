## Step 1: Company/filing lookup

### How this step works

**`filings.py` -> `resolve_cik(ticker)`**
1. Take a ticker symbol as input.
   > 中文：输入一个股票代码。
2. Download SEC's `company_tickers.json`, which lists every ticker with its CIK.
   > 中文：下载 SEC 提供的 `company_tickers.json` 文件，里面列出了所有股票代码及其对应的 CIK。
3. Loop through the entries looking for one whose ticker matches (case-insensitive).
   > 中文：遍历这些记录，查找股票代码匹配的那一条（不区分大小写）。
4. Format the matching CIK as a zero-padded 10-digit string and return it; raise an error if no match is found.
   > 中文：把匹配到的 CIK 格式化成 10 位数字（前面补零）并返回；如果找不到匹配项，则抛出错误。

**`filings.py` -> `get_latest_10k_filings(ticker, count=2)`**
1. Call `resolve_cik(ticker)` to get the company's CIK.
   > 中文：调用 `resolve_cik(ticker)` 获取公司对应的 CIK。
2. Download that company's filing history from the SEC submissions API.
   > 中文：通过 SEC 的 submissions API 下载该公司的历史文件列表。
3. Walk through the filings in order, keeping only the ones whose form type is "10-K".
   > 中文：按顺序遍历所有文件记录，只保留表格类型为 "10-K" 的那些。
4. For each matching filing, strip the dashes from its accession number and build the full document URL.
   > 中文：对每一条匹配的记录，去掉 accession number 里的横线，拼出完整的文件网址。
5. Stop once `count` filings have been collected and return each one's year, accession number, and document URL.
   > 中文：收集到 `count` 份文件后停止，并返回每份文件的年份、accession number 和文件网址。

### Terms

- **CIK (Central Index Key)** — the unique ID SEC assigns to every company/filer, used instead of the ticker in most EDGAR API URLs.
  > 中文：CIK 是美国证券交易委员会（SEC）给每个上市公司分配的唯一编号，类似于公司的身份证号。EDGAR 的大部分接口都是用 CIK 而不是股票代码（ticker）来查询数据，所以拿到股票代码后第一步要先换算成 CIK。

- **`company_tickers.json`** — a single static file SEC publishes listing every ticker with its CIK and company name; it's the lookup table used to go from ticker → CIK.
  > 中文：这是 SEC 提供的一个静态 JSON 文件，里面列出了所有股票代码对应的 CIK 和公司名称。可以把它理解成一张"股票代码对照表"，我们从这里查到公司对应的 CIK。

- **Submissions API (`data.sec.gov/submissions/CIK##########.json`)** — a per-company endpoint that returns that company's full filing history (form types, dates, accession numbers, document filenames) once you know its CIK.
  > 中文：知道 CIK 之后，就可以访问这个接口获取该公司所有历史文件的清单，包括每份文件的类型（比如 10-K）、日期、编号和文件名。这是第二步查询，在拿到 CIK 之后才能用。

- **Accession number** — the unique ID SEC assigns to one specific filing submission; formatted with dashes (e.g. `0001652044-26-000018`) but the dashes must be stripped to build the filing's folder URL on EDGAR.
  > 中文：accession number 是 SEC 给每一次"提交的文件"分配的唯一编号，带有横线（比如 0001652044-26-000018）。但是在拼接文件存放的网址时，需要把横线去掉，否则链接会失效。

- **`User-Agent` header requirement** — SEC requires every automated request to identify who's making it (app name + contact email) via the `User-Agent` header, or requests may be blocked/rate-limited.
  > 中文：SEC 要求所有自动化程序访问它的接口时，都要在请求头里表明"是谁在访问"（比如程序名 + 联系邮箱），否则可能会被限流或拒绝访问。这是 SEC 的使用规范，不是 Python 本身的要求。

- **Zero-padding with `f"{n:010d}"`** — a Python f-string format spec that pads an integer with leading zeros to a fixed width (10 digits here); needed because SEC's CIK-based URLs expect exactly 10 digits, but the raw CIK number from the JSON file has no leading zeros.
  > 中文：`f"{n:010d}"` 是 Python 格式化字符串的写法，表示把整数 n 补零到 10 位。因为从 JSON 里读出来的 CIK 是普通数字（没有前导零），但 SEC 的网址要求必须是 10 位数字，所以需要手动补零。

## Step 2: Ingestion

### How this step works

**`ingest.py` -> `extract_text(html)`**
1. Take the raw HTML of a filing as input.
   > 中文：输入一份文件的原始 HTML。
2. Parse it with BeautifulSoup and remove all `<script>` and `<style>` tags, since their content isn't real page text.
   > 中文：用 BeautifulSoup 解析 HTML，并删除所有 `<script>` 和 `<style>` 标签，因为这些标签里的内容不是真正的正文文字。
3. Return the remaining visible text, with each HTML element's text separated by a newline.
   > 中文：返回剩下的可见文字，每个 HTML 元素之间用换行符隔开。

**`ingest.py` -> `chunk_text(text, chunk_size=500, overlap=50)`**
1. Take a block of text and encode it into tokens using tiktoken.
   > 中文：输入一段文字，用 tiktoken 把它编码成 token（词元）序列。
2. Slide a window of `chunk_size` tokens across the token sequence, moving forward by `chunk_size - overlap` tokens each time so consecutive windows overlap.
   > 中文：在 token 序列上滑动一个长度为 `chunk_size` 的窗口，每次向前移动 `chunk_size - overlap` 个 token，让相邻的两个窗口有重叠部分。
3. Decode each window of tokens back into text and collect them into a list of chunks.
   > 中文：把每个窗口里的 token 解码回文字，收集成一个分块（chunk）列表。

**`ingest.py` -> `ingest_ticker(ticker)`**
1. Check whether a cache file for this ticker already exists under `data/`; if so, load it and return it immediately, with no network calls.
   > 中文：检查 `data/` 目录下是否已经有这个股票代码的缓存文件；如果有，直接读取并返回，不再发起任何网络请求。
2. Otherwise, call `get_latest_10k_filings(ticker)` (from step 1) to get the filing URLs.
   > 中文：如果没有缓存，就调用第一步写的 `get_latest_10k_filings(ticker)` 获取文件网址。
3. Download each filing's HTML, run it through `extract_text` then `chunk_text`, and tag every resulting chunk with its ticker and filing year.
   > 中文：下载每份文件的 HTML，依次调用 `extract_text` 和 `chunk_text` 处理，并给每个生成的分块打上股票代码和年份标签。
4. Save the combined list of chunks to the cache file as JSON, then return it.
   > 中文：把所有分块合并成一个列表，保存为 JSON 缓存文件，然后返回这个列表。

### Terms

- **BeautifulSoup / `get_text()`** — a library for parsing HTML and pulling out its structure or text; `get_text()` walks the parsed page and concatenates all the visible text, skipping tags themselves.
  > 中文：BeautifulSoup 是一个用来解析 HTML 的库，可以方便地提取网页结构或文字。`get_text()` 方法会遍历解析后的页面，把所有可见文字拼接起来，跳过标签本身。

- **tiktoken (`encode`/`decode`)** — the tokenizer library used by OpenAI-style models; `encode()` turns text into a list of integer token IDs, `decode()` turns token IDs back into text. Chunking by tokens (not characters) keeps chunk sizes consistent with what the embedding/chat models actually "see."
  > 中文：tiktoken 是 OpenAI 系模型使用的分词工具。`encode()` 把文字转换成一串整数 token ID，`decode()` 则反过来把 token ID 还原成文字。按 token（而不是字符）来分块，能让分块大小和嵌入/对话模型实际处理的单位保持一致。

- **Sliding-window chunking with overlap** — splitting a long text into fixed-size, overlapping chunks so that context near a chunk boundary isn't lost entirely to just one side.
  > 中文：滑动窗口分块法是把一段长文字切成固定大小、且相邻窗口有重叠的若干块，这样边界附近的上下文不会完全只出现在一个分块里，检索时更不容易丢失信息。

- **Cache-by-ticker pattern** — check for an existing on-disk result before doing expensive work (network calls, parsing); if found, skip straight to returning it.
  > 中文：按股票代码缓存的模式：在做耗时的操作（网络请求、解析）之前，先检查本地是否已经有结果文件；如果有，就直接返回，跳过重复劳动。

- **`Path.mkdir(exist_ok=True)`** — creates a directory if it doesn't already exist, and does nothing (instead of raising an error) if it does.
  > 中文：`Path.mkdir(exist_ok=True)` 用来创建一个目录；如果目录已经存在，就什么都不做，而不会报错。
