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

## Step 3: Embedding

### How this step works

**`embed.py` -> `embed_texts(texts)`**
1. Split the list of texts into fixed-size batches, since the API accepts many inputs per call but has request-size limits.
   > 中文：把文字列表切分成固定大小的批次，因为 API 一次调用能接受多条输入，但对单次请求的大小有限制。
2. For each batch, send it to OpenAI's embeddings endpoint and wait for a response.
   > 中文：对每一批，发送到 OpenAI 的 embeddings 接口并等待返回结果。
3. If the response says "rate limited" (HTTP 429), wait a bit and retry the same batch, up to a few attempts.
   > 中文：如果返回结果提示"请求过于频繁"（HTTP 429），就等待一小段时间后重试同一批，最多重试几次。
4. Once a batch succeeds, pull out each input's embedding vector from the response and add it to the running list.
   > 中文：一批成功后，从返回结果里取出每条输入对应的向量，加入到结果列表中。
5. After all batches are done, return the full list of embedding vectors, in the same order as the input texts.
   > 中文：所有批次都处理完后，按照输入文字的原始顺序，返回完整的向量列表。

**`embed.py` -> `embed_ticker(ticker)`**
1. Normalize the ticker to uppercase, then check the Chroma collection for any chunk already tagged with that ticker in its metadata.
   > 中文：把股票代码转成大写，然后在 Chroma 集合里查一下有没有分块的元数据已经标记了这个股票代码。
2. If a match is found, everything for this ticker is already embedded and stored, so return immediately with no API calls.
   > 中文：如果查到了匹配的记录，说明这个股票代码已经生成过向量并存好了，直接返回，不再调用任何 API。
3. Otherwise, get the ticker's chunks by calling `ingest_ticker(ticker)` (from step 2), then call `embed_texts` on every chunk's text to get their vectors.
   > 中文：如果没查到，就调用第二步写的 `ingest_ticker(ticker)` 获取该股票代码的分块，再对所有分块的文字调用 `embed_texts` 生成向量。
4. Add all chunks to the Chroma collection in one call: each chunk's vector, its text, and its metadata (ticker, year), each tagged with a unique id.
   > 中文：把所有分块一次性写入 Chroma 集合：包括每个分块的向量、原文和元数据（股票代码、年份），并给每条记录配一个唯一 id。

### Terms

- **Embedding** — a vector (list of numbers) that represents the meaning of a piece of text, produced by a model trained for this purpose; texts with similar meaning end up with similar vectors, which is what makes similarity search possible later.
  > 中文：embedding（嵌入向量）是用一个专门训练的模型，把一段文字转换成一串数字（向量），代表这段文字的语义。意思相近的文字，生成的向量也会比较接近，这就是后面能做相似度搜索的基础。

- **Batching requests** — sending several inputs in a single API call instead of one call per input, to reduce the number of network round trips and stay efficient.
  > 中文：批处理请求指的是一次 API 调用里发送多条输入，而不是每条输入都单独调用一次，这样能减少网络请求次数，效率更高。

- **HTTP 429 (rate limited) + retry with backoff** — a status code meaning "you're sending requests too fast"; the standard fix is to pause briefly and try again, rather than treating it as a real failure.
  > 中文：HTTP 429 表示"请求发送得太快了"；标准做法是暂停一小段时间后重试，而不是把它当成真正的错误直接放弃。

- **Caching by content presence (`collection.get(where=..., limit=1)`)** — checking whether any record already exists for a ticker, rather than tracking a separate "is this done" flag, is a simple way to make a step skippable if it already ran; this replaced an earlier version that checked for an `"embedding"` field on the cached chunk data instead (see Step 4's "Revision" below for why the storage moved to Chroma).
  > 中文：通过查一下 Chroma 里是否已经有某个股票代码的记录（`collection.get(where=..., limit=1)`），而不是单独维护一个"是否完成"的标记，是判断某一步是否已经跑过、可以跳过的简单方法；这取代了之前"检查分块数据里有没有 `embedding` 字段"的做法（原因见第 4 步下面的"修订"部分）。

- **Chroma / vector database** — a database purpose-built for storing embedding vectors and searching them by similarity, instead of a plain file; `chromadb.PersistentClient(path=...)` runs it embedded in the same process (no separate server) and persists everything to disk under that path.
  > 中文：Chroma 是一个专门用来存储向量（embedding）并按相似度搜索的数据库，而不是普通的文件。`chromadb.PersistentClient(path=...)` 让它直接嵌入在当前程序里运行（不需要单独启动服务器），并把所有数据持久化保存到指定路径下。

- **Collection** — a named table-like grouping inside Chroma that holds vectors, their original text (`documents`), and arbitrary metadata (like `ticker`, `year`) side by side; `get_or_create_collection` opens it if it exists or creates it on first use.
  > 中文：collection（集合）是 Chroma 里类似"表"的概念，把向量、原文（`documents`）和自定义元数据（比如 `ticker`、`year`）存放在一起。`get_or_create_collection` 会在集合已存在时打开它，不存在时自动创建。

- **Metadata filtering (`where={"ticker": ...}`)** — Chroma lets a query or a `get`/`delete` call be restricted to only the records whose metadata matches a filter, which is what makes "only this ticker's chunks" possible without loading everything and filtering by hand in Python.
  > 中文：`where={"ticker": ...}` 是 Chroma 提供的元数据筛选功能，可以让查询、`get`、`delete` 只作用于元数据匹配条件的那些记录，这样就能直接拿到"某个股票代码自己的分块"，不需要把所有数据加载出来再用 Python 手动筛选。

## Step 4: Retrieval

### How this step works

**`retrieve.py` -> `retrieve(question, tickers=("GOOGL", "MU"), top_k=5)`**
1. For each ticker, call `embed_ticker(ticker)` (from step 3) first, so its chunks are guaranteed to already be embedded and stored in Chroma before querying.
   > 中文：对每个股票代码，先调用第三步写的 `embed_ticker(ticker)`，确保在查询之前，它的分块已经生成向量并存进了 Chroma。
2. Embed the user's question once, with the same embedding function used for the chunks, so both are in the same vector space.
   > 中文：把用户的问题转换成向量（用和分块一样的 embedding 函数），这样问题向量和分块向量才能放在一起比较。
3. For each ticker separately: query the Chroma collection for the top `top_k` chunks whose metadata ticker matches, using the question vector for similarity search.
   > 中文：对每一个股票代码单独处理：用问题向量去查询 Chroma 集合，只在该股票代码对应的分块里取相似度最高的 top `top_k` 个。
4. Convert each result's distance back into a similarity-style score (`1 - distance`), so a higher number still means "more similar", matching the old convention.
   > 中文：把每条结果的 distance（距离）转换回类似相似度的分数（`1 - distance`），这样分数越高仍然代表越相似，和之前的写法保持一致。
5. Repeat for every ticker, so each one contributes its own top `top_k` chunks — this still guarantees every ticker is represented, instead of one global ranking where a lower-scoring ticker could be crowded out entirely.
   > 中文：对每个股票代码都重复这个过程，这样每个股票代码都能贡献自己的 top `top_k` 个分块——依然能保证每个股票代码都有代表性，而不是用一个全局排名，让分数普遍较低的那个股票代码被完全挤掉。
6. Merge all tickers' chunks into one list, sort the merged list by score (highest first), and return it (ticker, year, text, score).
   > 中文：把所有股票代码的分块合并成一个列表，按分数从高到低排序后返回（包含股票代码、年份、文字、分数）。

### Revision: before vs. after (the cross-company retrieval fix)

The original version of `retrieve()` is kept, commented out, at the top of `retrieve.py` for comparison.

- **Before**: combined every ticker's chunks into one pool, computed similarity for all of them against the question, and took a single global top `top_k` across that whole pool.
  > 中文：旧版本把所有股票代码的分块合并成一个池子，统一计算每个分块和问题的相似度，然后从这个大池子里取一个全局的 top `top_k`。

- **Problem this caused**: for a cross-company question, if one company's chunks happened to score higher overall, the global top `top_k` could end up filled entirely (or almost entirely) with that one company's chunks — the other company's data might never make it into the context at all, even though the question needed both. Confirmed in evaluation: all 3 cross-company eval questions failed this way.
  > 中文：这样做的问题是：对于跨公司的问题，如果某一家公司的分块整体相似度更高，全局 top `top_k` 就可能几乎全被这一家公司的分块占满——另一家公司的数据可能完全进不了上下文，即使问题明明需要两家公司的数据。在评测中验证到：3 道跨公司问题全部因此失败。

- **After**: compute similarity and take the top `top_k` separately *within* each ticker's own pool first, then merge all tickers' results together.
  > 中文：新版本先在每个股票代码*各自的*分块池子里分别计算相似度、取各自的 top `top_k`，然后再把所有股票代码的结果合并起来。

- **Result**: every ticker is now guaranteed to contribute up to `top_k` chunks, regardless of how its scores compare to another ticker's. Re-running the evaluation confirmed all 3 cross-company questions now retrieve and use both companies' data correctly.
  > 中文：这样一来，无论某个股票代码整体分数高低，都能保证它贡献最多 `top_k` 个分块。重新跑评测后确认：3 道跨公司问题现在都能正确取到并使用两家公司的数据了。

### Revision: before vs. after (numpy/JSON → Chroma)

The numpy/cosine-similarity version — both storing embeddings in each ticker's chunk JSON file and computing
similarity by hand — is kept, commented out, in `embed.py` and `retrieve.py` for comparison.

- **Before**: `embed_ticker` wrote each chunk's vector back into that ticker's chunk JSON cache file (the same file used for step 2's text chunks), checked by looking for an `"embedding"` field on the first chunk. `retrieve` then loaded that whole file per ticker, stacked every chunk's vector into a numpy array, and computed cosine similarity by hand against the question vector.
  > 中文：旧版本里，`embed_ticker` 把每个分块的向量直接写回该股票代码的分块 JSON 缓存文件（和第二步存文字分块用的是同一个文件），并通过检查第一个分块有没有 `"embedding"` 字段来判断是否已经处理过。`retrieve` 检索时要把整个文件加载进来，把所有分块的向量堆叠成一个 numpy 数组，再手动计算和问题向量的余弦相似度。

- **Why upgrade**: a flat JSON file has no built-in indexing or metadata filtering — it works fine at a few hundred chunks, but every single query still means loading the whole file and comparing against every vector by hand in Python. A vector database like Chroma is the kind of infrastructure real production RAG systems actually run on: it persists embeddings to disk itself, indexes them for similarity search, and supports metadata filtering (`where={"ticker": ...}`) natively — so the per-ticker retrieval no longer needs to be hand-rolled with numpy, and there's real room to grow past a few hundred chunks without rewriting retrieval again.
  > 中文：普通的 JSON 文件没有内置索引，也没办法按元数据筛选——在只有几百个分块的规模下能用，但每次查询仍然要把整个文件加载出来，在 Python 里逐个手动比较。Chroma 这样的向量数据库才是真实生产环境里 RAG 系统会用的基础设施：它自己把向量持久化到磁盘、为相似度搜索建好索引，并且原生支持按元数据筛选（`where={"ticker": ...}`）——这样按股票代码分别检索的逻辑就不用再靠 numpy 手写了，而且未来分块数量远超几百个也不需要重写检索逻辑。

- **After**: `embed_ticker` now writes each chunk's vector, text, and metadata into a Chroma collection persisted under `data/chroma`, checked for an existing ticker via `collection.get(where=...)` instead of an `"embedding"` field. `retrieve` queries that same collection per ticker (`collection.query(..., where={"ticker": ticker})`) instead of loading and comparing vectors by hand.
  > 中文：现在 `embed_ticker` 把每个分块的向量、原文和元数据写进一个持久化在 `data/chroma` 目录下的 Chroma 集合，并通过 `collection.get(where=...)` 检查该股票代码是否已经存在，而不是看 `"embedding"` 字段。`retrieve` 则对同一个集合按股票代码分别查询（`collection.query(..., where={"ticker": ticker})`），不再需要手动加载和比较向量。

- **Result**: re-ran the full evaluation after switching to Chroma. All 3 cross-company questions still correctly retrieve and use both companies' data, and the RAG triad scores stayed consistent with the numpy version: groundedness 1.00 → 1.00, answer relevance 1.00 → 1.00, context relevance 0.78 → 0.83 (a small, expected fluctuation from the LLM judge, not a retrieval change — the underlying cosine-similarity math and per-ticker guarantee are identical, just computed by Chroma's index instead of by hand). Confirms the swap changed the storage/query mechanism without hurting retrieval quality.
  > 中文：切换到 Chroma 之后重新跑了一次完整评测。3 道跨公司问题依然能正确取到并使用两家公司的数据，RAG triad 的分数也和 numpy 版本基本一致：忠实度 1.00 → 1.00，答案相关性 1.00 → 1.00，上下文相关性 0.78 → 0.83（这只是 LLM 评委带来的小幅波动，不是检索本身变了——底层的余弦相似度计算和"每个股票代码都有保证"这两点完全没变，只是换成由 Chroma 的索引来计算，而不是手写代码算）。确认这次改动只是换了存储和查询方式，没有影响检索质量。

### Terms

- **Cosine similarity** — a way to measure how similar two vectors are, based on the angle between them (not their length); a score of 1 means identical direction (very similar meaning), 0 means unrelated. It's computed as the dot product of the two vectors divided by the product of their lengths (norms).
  > 中文：余弦相似度用来衡量两个向量有多相似，看的是它们之间的夹角（而不是长度）。分数为 1 表示方向完全一致（意思非常接近），0 表示没什么关系。计算方式是两个向量的点积，除以它们各自长度（范数）的乘积。

- **Vectorized operation (numpy)** — doing a calculation on an entire array/matrix at once (e.g. `chunk_vectors @ question_vector`) instead of looping over each element in Python; numpy runs this in fast, compiled code under the hood, which is much quicker than a manual loop.
  > 中文：向量化操作指的是用 numpy 一次性对整个数组/矩阵做运算（比如 `chunk_vectors @ question_vector`），而不是在 Python 里写循环逐个处理。numpy 底层用编译好的代码执行，速度比手写循环快得多。

- **`np.linalg.norm`** — computes the length (magnitude) of a vector; used here to normalize the dot product into a proper cosine similarity score.
  > 中文：`np.linalg.norm` 用来计算一个向量的长度（模）。这里用它把点积结果归一化，转换成真正的余弦相似度分数。

- **`np.argsort`** — returns the indices that would sort an array, rather than the sorted values themselves; combined with `[::-1]` (reverse) and slicing `[:top_k]`, it gives the indices of the highest-scoring chunks. (This was used by the old numpy version, kept commented out for comparison; the current version lets Chroma's own index do the ranking instead.)
  > 中文：`np.argsort` 返回的是"排序后各元素原来所在的位置下标"，而不是排序后的数值本身。配合 `[::-1]`（反转顺序）和切片 `[:top_k]`，就能拿到分数最高的几个分块对应的下标。（这是旧版 numpy 实现用的写法，保留在注释里做对比；现在的版本改成直接让 Chroma 自己的索引来排序。）

- **Cosine distance vs. cosine similarity (`score = 1 - distance`)** — Chroma's `query()` returns a *distance* (smaller = more similar), not a similarity score; with the collection configured for cosine space, that distance equals `1 - cosine_similarity`, so subtracting it from 1 converts it back into the same "higher = more similar" score used everywhere else in this project.
  > 中文：Chroma 的 `query()` 返回的是"距离"（distance，数值越小越相似），不是相似度分数；因为集合设置成了余弦空间，这个距离正好等于 `1 - 余弦相似度`，所以用 1 减去它，就能换算回项目里其它地方统一用的"分数越高越相似"的写法。

## Step 5: Generation

### How this step works

**`generate.py` -> `answer(question, top_k=5)`**
1. Call `retrieve(question, top_k=top_k)` (from step 4) to get the most relevant filing chunks.
   > 中文：调用第四步写的 `retrieve(question, top_k=top_k)`，获取最相关的那些分块。
2. Join those chunks into one text block, each one labeled with its ticker and filing year.
   > 中文：把这些分块拼接成一段文字，每个分块前面标注上对应的股票代码和年份。
3. Build a chat message list: a system instruction telling the model to answer only from the excerpts (and say "I don't know" otherwise), plus a user message containing the excerpts and the question.
   > 中文：组装一个对话消息列表：一条系统指令，要求模型只根据这些摘录回答问题（否则就说"不知道"），再加一条用户消息，里面包含摘录内容和问题本身。
4. Send those messages to OpenAI's chat completions API using the `gpt-4.1-mini` model.
   > 中文：把这些消息发送给 OpenAI 的 chat completions 接口，使用 `gpt-4.1-mini` 模型。
5. Pull the model's reply text out of the response and return it.
   > 中文：从返回结果中取出模型回复的文字内容，返回给调用者。

### Terms

- **Prompt stuffing** — putting retrieved context text directly into the prompt sent to the LLM, so it can "read" that information before answering; this is the core mechanic of RAG (retrieval-augmented generation).
  > 中文：prompt stuffing（提示词填充）指的是把检索到的内容直接放进发给大模型的提示词里，让模型在回答之前先"读到"这些信息。这正是 RAG（检索增强生成）的核心机制。

- **System vs. user message** — chat models take a list of role-tagged messages; a "system" message sets behavior/rules for the whole conversation, while a "user" message is the actual input/question. Separating them keeps instructions (don't guess, use only the context) distinct from the content being asked about.
  > 中文：对话模型接收的是一系列带角色标签的消息；"system"（系统）消息用来设定整段对话的行为规则，"user"（用户）消息则是具体的输入/问题。把两者分开，能让"不要瞎猜、只用给定内容回答"这类规则和实际问题内容区分清楚。

- **Grounding / abstention instruction** — explicitly telling the model to answer only from provided context and to say "I don't know" when the answer isn't there, instead of relying on its own general knowledge — this reduces hallucination and is what a should-abstain eval question later checks for.
  > 中文：grounding（依据信息作答）/ 拒答指令，是明确告诉模型"只能根据提供的内容回答，如果里面没有答案就说不知道"，而不是依赖模型自己的通用知识瞎猜——这样能减少"幻觉"，也是之后评测里"应该拒答"的问题要检验的能力。

## Step 6: Evaluation

### How this step works

**`eval.py` -> `get_cached_answer(question, cache)`**
1. Build a cache key from the retrieval method and the question.
   > 中文：用检索方法的名字加上问题本身，拼出一个缓存的键（key）。
2. If that key isn't in the cache yet, call `answer(question)` (from step 5) and store the result under that key, saving the cache to disk right away.
   > 中文：如果这个键还没有出现在缓存里，就调用第五步写的 `answer(question)` 生成答案，并把结果存进缓存，同时立刻写入磁盘保存。
3. Return whatever is now stored under that key — either the freshly generated result, or the one that was already cached.
   > 中文：返回这个键目前对应的结果——不管是刚刚生成的，还是之前就已经缓存好的。

**`eval.py` -> `run_eval()`**
1. Load the on-disk answer cache and set up the three RAG-triad evaluators (context relevance, groundedness, answer relevance) backed by `gpt-4.1-mini` as the judge model.
   > 中文：读取磁盘上的答案缓存，并准备好三个 RAG triad 评估器（上下文相关性、忠实度、答案相关性），它们都用 `gpt-4.1-mini` 作为"评委"模型。
2. For each question in the hand-written eval set, get its answer via `get_cached_answer` (generating it only if not already cached).
   > 中文：对于手写评测集里的每一个问题，通过 `get_cached_answer` 获取答案（只有没缓存过才会真的调用模型生成）。
3. Run all three evaluators on the (question, answer, retrieved context) triple, producing a relevance/faithfulness label and score for each.
   > 中文：对（问题、答案、检索到的上下文）这一组数据，跑三个评估器，得到每一项的标签（比如"相关"或"不相关"）和分数。
4. Print the question, its answer, the three scores, and the token usage/latency for that question.
   > 中文：打印出问题、答案、三个评分结果，以及这道题消耗的 token 数量和用时。
5. Collect all per-question results into a list and return it, for the final summary to aggregate.
   > 中文：把每道题的结果收集成一个列表并返回，供最后的汇总统计使用。

### Terms

- **RAG triad** — three reference-free metrics used to evaluate a RAG system without needing a hand-written "correct answer": context relevance (is the retrieved context relevant to the question?), groundedness/faithfulness (is the answer actually supported by that context?), and answer relevance (does the answer address the question asked?).
  > 中文：RAG triad（RAG 三元组指标）是三个不需要人工写"标准答案"就能评估 RAG 系统的指标：上下文相关性（检索到的内容和问题相关吗？）、忠实度/依据性（答案是不是真的有上下文支持？）、答案相关性（答案有没有回应问题本身？）。

- **LLM-as-judge** — using a language model to score another model's output (instead of a human or a fixed rule), by giving the judge model the question/answer/context and asking it to classify or rate the result.
  > 中文：LLM-as-judge（用大模型当评委）指的是用一个语言模型去给另一个模型的输出打分（而不是靠人工或写死的规则），做法是把问题、答案、上下文都给这个"评委"模型，让它做分类或打分。

- **Phoenix's `LLM` wrapper / `Evaluator` classes** — `arize-phoenix-evals` provides a small `LLM` wrapper around a real provider (here, OpenAI) plus prebuilt `Evaluator` classes (like `FaithfulnessEvaluator`, `RetrievalRelevanceEvaluator`) that already contain a tested judge prompt for a specific metric — so a metric doesn't need to be built from scratch.
  > 中文：`arize-phoenix-evals` 提供了一个包装真实模型提供商（这里是 OpenAI）的 `LLM` 类，以及一些内置的 `Evaluator`（评估器）类（比如 `FaithfulnessEvaluator`、`RetrievalRelevanceEvaluator`），它们已经内置了针对特定指标、经过验证的评分提示词，不需要自己从零写。

- **`create_classifier`** — a factory function for building a *custom* LLM-as-judge classifier when Phoenix doesn't ship a prebuilt evaluator for what's needed (here, "answer relevance"); you give it a name, a judge prompt template, and the possible labels/scores.
  > 中文：`create_classifier` 是一个用来构建*自定义* LLM 评委分类器的工厂函数，用在 Phoenix 没有现成评估器的场景（这里是"答案相关性"）；只需要提供名字、评分用的提示词模板，以及可能的标签和分数。

- **Caching LLM answers per (question, retrieval method)** — storing each generated answer keyed by both the question text and which retrieval method produced its context, so re-running the eval script (e.g. after changing an evaluator) doesn't re-spend money regenerating unchanged answers.
  > 中文：按照"问题 + 检索方法"这个组合来缓存每次生成的答案，这样以后重新跑评测脚本（比如只是改了评分逻辑）时，不会为没有变化的问题重新花钱生成答案。

## Step 7: Hybrid retrieval

### How this step works

**`retrieve.py` -> `retrieve(question, tickers=("GOOGL", "MU"), top_k=5, method="hybrid")`**
1. Check that `method` is `"vector"` or `"hybrid"`, and raise an error for anything else.
   > 中文：先检查 `method` 是不是 `"vector"` 或 `"hybrid"`，如果是其他值就直接报错。
2. Make sure every ticker's chunks are embedded and stored in Chroma (`embed_ticker`), then embed the question once.
   > 中文：确保每个股票代码的分块都已经生成向量并存进 Chroma（`embed_ticker`），然后把问题转成向量（只做一次）。
3. For each ticker separately, ask Chroma for the 20 closest chunk ids by vector similarity.
   > 中文：对每个股票代码单独处理：向 Chroma 查询向量相似度最高的 20 个分块的 id。
4. Get that ticker's BM25 index (`_bm25_index`), score every chunk against the tokenized question, and keep the top 20 chunk ids that have a score above 0.
   > 中文：取出该股票代码的 BM25 索引（`_bm25_index`），用分词后的问题给每个分块打分，保留得分大于 0 的前 20 个分块 id。
5. Fuse the two ranked id lists with `rrf_fuse`, keep the top `top_k`, and look up each chunk's text, ticker, and year.
   > 中文：用 `rrf_fuse` 把两个排好序的 id 列表融合，保留前 `top_k` 个，再查出每个分块的文字、股票代码和年份。
6. Merge every ticker's results, sort them by RRF score (highest first), and return them in the same shape as vector search.
   > 中文：合并所有股票代码的结果，按 RRF 分数从高到低排序后返回，返回格式和纯向量检索完全一样。

**`retrieve.py` -> `_bm25_index(ticker)`**
1. If this ticker's index is already in the in-memory cache, return it.
   > 中文：如果这个股票代码的索引已经在内存缓存里，直接返回。
2. Otherwise, load all of that ticker's chunks (ids, text, metadata) from Chroma with `collection.get`.
   > 中文：否则，用 `collection.get` 从 Chroma 读出这个股票代码的全部分块（id、文字、元数据）。
3. Tokenize every chunk and build a `BM25Okapi` index from the token lists.
   > 中文：把每个分块分词，用这些词列表建立一个 `BM25Okapi` 索引。
4. Cache the index together with the ids, texts, and metadata, then return them.
   > 中文：把索引和 id、文字、元数据一起放进缓存，然后返回。

**`retrieve.py` -> `tokenize(text)`**
1. Lowercase the text, then split it into word tokens with `re.findall(r"\w+")`, so numbers ("257") and terms ("hbm") each become their own token.
   > 中文：把文字转成小写，再用 `re.findall(r"\w+")` 切成单词，这样数字（比如 "257"）和术语（比如 "hbm"）都会成为独立的词。

**`retrieve.py` -> `rrf_fuse(rank_lists, k=60)`**
1. For every ranked list, give each chunk id `1 / (k + rank)` points, where rank starts at 1.
   > 中文：对每个排好序的列表，给每个分块 id 加上 `1 / (k + 排名)` 分（排名从 1 开始）。
2. Add up each id's points across all lists, so an id that appears in both lists gets points twice.
   > 中文：把同一个 id 在所有列表里的得分加起来，所以同时出现在两个列表里的 id 会得到两次分数。
3. Return `(id, score)` pairs sorted from highest to lowest score.
   > 中文：返回按分数从高到低排序的 `(id, 分数)` 列表。

**`eval.py` -> `run_eval(method="vector", eval_set=EVAL_SET)`**
1. Same as Step 6, except the retrieval method and question set are now parameters (`--method`, `--set` on the command line), and the cache key is `"<method>::<question>"`, so vector and hybrid answers never overwrite each other.
   > 中文：和第六步一样，只是检索方法和题目集变成了参数（命令行用 `--method`、`--set` 指定），缓存键变成 `"方法::问题"`，所以向量检索和混合检索的答案不会互相覆盖。

### Terms

- **BM25** — a classic keyword-search scoring formula: a chunk scores higher when it contains the question's words, especially rare ones, with diminishing returns for repeats and a penalty for very long chunks.
  > 中文：BM25 是一种经典的关键词检索打分公式：分块里出现问题中的词越多，分数越高，尤其是稀有的词；同一个词重复很多次的收益会递减，太长的分块会被扣分。它擅长精确匹配，比如数字和专有名词。

- **Hybrid retrieval** — running keyword search (BM25) and semantic search (vectors) side by side and combining their results, so a chunk can be found either by meaning or by exact wording.
  > 中文：混合检索是同时跑关键词检索（BM25）和语义检索（向量），再把结果合并。这样一个分块既可以靠"意思相近"被找到，也可以靠"字面完全匹配"被找到。

- **Reciprocal Rank Fusion (RRF)** — a way to merge several ranked lists using only the positions (ranks), not the raw scores: each item gets `1/(60 + rank)` from each list it appears in, summed up.
  > 中文：RRF（倒数排名融合）是一种合并多个排序列表的方法，只看名次、不看原始分数：每个条目在它出现的每个列表里得到 `1/(60 + 名次)` 分，再加总。因为 BM25 分数和余弦相似度的量纲完全不同，只用名次就不需要做分数归一化。

- **Tokenizer** — the function that splits text into the words BM25 matches on. Here: lowercase, then `\w+` (runs of letters, digits, and underscores).
  > 中文：分词器（tokenizer）是把文字切成单词的函数，BM25 就是拿这些词去做匹配。这里的做法是先转小写，再用 `\w+`（连续的字母、数字、下划线）切分。注意 "$37.4" 会被切成 "37" 和 "4"，但问题和分块用的是同一种切法，所以仍然能匹配上。

- **Lazy in-memory index** — the BM25 index isn't saved to disk. It's built the first time a ticker is searched, then kept in a Python dict for the rest of the process.
  > 中文：懒加载的内存索引：BM25 索引不保存到磁盘，而是在第一次检索某个股票代码时才建立，之后在整个程序运行期间都保存在一个 Python 字典里。约 400 个分块建索引只需要很短时间，所以不值得额外做持久化。

- **Reference-free metric blind spot** — the RAG triad doesn't know the correct answer, so a wrong "I don't know" can still pass all three metrics (it's grounded and on-topic). Checking against expected answers catches this.
  > 中文：无参考指标的盲点：RAG triad 不知道正确答案是什么，所以一个错误的"我不知道"仍然可能三项全部通过（因为它没有编造，也回应了问题）。只有拿预期答案去对比才能发现这种错误。
