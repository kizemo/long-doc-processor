# 内存安全 · 音视频处理红线

> **状态**：2026-10-24 起生效。所有处理音视频的步骤都必须遵守。
> 配套代码：`scripts/memory_guard.py`（护栏本体）、`scripts/transcribe_via_crv.py`、
> `scripts/asr_faster_whisper.py`。
> 回归测试：`tests/test_memory_guard.py`。

## 0 · 一句话

**所有处理音视频的子进程，都必须带一个内核级的 commit 硬上限；所有子进程输出，
都必须显式按 UTF-8 解码。**

---

## 1 · 为什么有这条红线（不是理论推演）

本机在同一台机器上被同一种故障打死过 4 次：

```
Microsoft-Windows-Resource-Exhaustion-Detector:
  ffmpeg.exe (19972) 使用了 107,276,828,672 字节
  SystemCommitCharge 125,142,462,464 / SystemCommitLimit 125,262,950,400
-> dwm.exe / TextInputHost.exe / ImeService.exe / ToDesk.exe 连锁分配失败
-> 桌面假死 + 输入法报错弹窗 + 远程控制服务「启动失败」再也拉不起来
```

四条复盘结论，**与具体工具无关**，所以在本技能里重做一遍：

| # | 结论 | 在本技能里的落地 |
|---|---|---|
| 1 | 根因不是 ffmpeg，是**子进程没有任何上限** | `memory_guard.run_guarded()` 给每个子进程装 Job Object 上限 |
| 2 | 危险形态是**间歇性**的（8 次炸 1 次） | 不能靠"这条命令看着安全"；上限必须无条件装 |
| 3 | **采样监控不是护栏**（20 ms 轮询拦不住分配风暴） | 只认内核强制：Job Object / RLIMIT_AS |
| 4 | 护栏必须装在**子进程启动前**，否则有竞态 | `CREATE_SUSPENDED → AssignProcessToJobObject → NtResumeProcess` |

## 2 · 红线清单

### R1 · 子进程必须有 commit 硬上限

```python
from memory_guard import run_guarded
rc, out, err, note = run_guarded(cmd, mem_limit_mb=8192, timeout=7200)
```

- `mem_limit_mb` 是**每个进程**的上限（`JOB_OBJECT_LIMIT_PROCESS_MEMORY` = 0x100）。
- 子进程会被继承进同一个 job，所以 crv 派生的 ffmpeg 子进程同样受约束。
- **不用** `JOB_OBJECT_LIMIT_JOB_MEMORY`（0x10）：嵌套 job 下它返回 87。
  agent 运行时会把子进程放进 job，嵌套是常态，job 级标志在两个宿主里表现不一致。

### R2 · 进程内重活必须给自己装上限

重活在**本进程**做时（faster-whisper 的 PyAV 解码 + ctranslate2 推理），没有子进程可包，
必须用 `install_self_memory_ceiling()`。实测：装上之后越限分配会得到普通的
`MemoryError`（可以干净地报错），而不是把机器拖死。

**峰值不是常数**：`faster-whisper` 用 PyAV 把**整条音轨**一次性解码成 16 kHz 单声道
float32 —— **64 KB/s**。一条 2 小时 16 分的讲座，光这一项就是 ~500 MB，而且它发生在
**模型加载之前**。所以：

```
峰值 ≈ 模型权重 + 片长秒数 × 64 KB ÷ 1024 × 1.3 + 512 MB
```

`memory_guard.estimate_asr_peak_mb()` 就是这个公式。**跑之前先算账**（预算层），
超了就拒绝启动 —— 错误必须发生在任何大额分配之前。

### R3 · 子进程输出必须显式 UTF-8 解码

```python
subprocess.run(cmd, capture_output=True, text=True,
               encoding="utf-8", errors="replace")   # ✅
subprocess.run(cmd, capture_output=True, text=True)  # ❌
```

本机 `locale.getpreferredencoding()` 是 **cp936(GBK)**。用 `text=True` 却不指定
encoding 时，子进程输出会按 GBK 解码 —— 输出里一个 GBK 非法字节就能让
**读取线程**抛 `UnicodeDecodeError`，整步直接崩。

这不是理论问题：本技能的 4 处 `subprocess.run` 全部踩在这个坑上（2026-10-24 已修）。
`memory_guard._decode()` 已经处理了这个：先试 UTF-8，失败退回 mbcs，再失败就 replace。

### R4 · 长任务的输出不要在父进程内存里攒

一场两小时的 ASR 会打印很多。`capture_output=True` 会把它全留在父进程内存里。
用 `run_guarded(..., log_path=...)` 让子进程直接写文件，父进程只读尾部。

### R5 · 长音频必须**窗口化**转写（2026-10-24 实测事故）

**现象**：一条 2 小时 16 分的素材，跑 faster-whisper 直接崩：

```
numpy._ArrayMemoryError: Unable to allocate 1.19 GiB for an array
with shape (1, 799487, 400) and data type float32
```

**根因**：faster-whisper 1.2.1 的 `transcribe()` 无论传不传 `chunk_length`，
都会对**整条音轨**做一次 STFT：

```python
features = self.feature_extractor(audio, chunk_length=chunk_length)
```

而 `FeatureExtractor.__call__` 里 `chunk_length` 只改 `n_samples` / `nb_max_frames`
（补零窗口），**不改 STFT 的分段**。于是长音频的峰值是：

| 中间量 | 大小 |
|---|---|
| `stft` complex64 (1, 799487, 400) | ≈ 2.56 GB |
| `.astype("complex64")` 副本 | ≈ 2.56 GB |
| `magnitudes` float32 | ≈ 1.28 GB |
| `mel_spec` / `log_spec` | ≈ 0.30 GB |
| **合计** | **≈ 6.5 GB，一次性分配** |

≈ 810 KB / 秒音频。一条 8152 秒的片子 ≈ 6.6 GB，**与片长线性相关**。

**修法**：自己按窗口切片再逐段转写（`scripts/asr_faster_whisper.py` 现在就是这么做的，
`--split-seconds`，默认 600 s）。每段的 STFT 只占几 MB，
峰值变成「整条音轨的 float32（64 KB/s）+ 模型权重 + 一小段频谱」，**与片长无关**。
段与段的时间戳按偏移量拼回去（实测 3 窗口拼接时间戳 0 处逆序）。

> ⚠️ crv 0.10.x **没有**做窗口化（它直接调 faster-whisper 的整轨 API），
> 所以长视频走 crv 这条路径时峰值会到 9~10 GB。这也是为什么默认上限给到 16 GB，
> 而不是 2 GB。

### R6 · 内存上限 ≠ 预算；CUDA context 要算进 commit

两个量级必须分开（ad-cut 那条线的成熟做法）：

| 层 | 含义 | 作用 |
|---|---|---|
| **预算层** | 按片长估算的峰值（`ASR_BUDGET_MB`，默认 6 GB） | 启动前拒绝不划算的任务 |
| **上限层** | 内核强制的硬顶（`DEFAULT_MEM_LIMIT_MB`，默认 16 GB） | 超过就死，但机器不动 |

**为什么上限不能设成 6 GB**：Windows 上 CUDA 的设备内存映射**计入进程 commit**，
一条 large-v3 + CUDA 的进程，光 CUDA context 就要 ~2 GB。
实测把上限设成 6 GB 时，模型刚加载完就 `MemoryError: bad allocation`——
连一个 1000 元素的数组都分配不出来。那不是保护，那是把功能改没了。

**教训**：上限要设在「正常峰值 + 足够余量」之上，让它只兜住**异常**，
而不是去卡住**正常的长任务**。

## 3 · 本技能里的具体调用点

| 位置 | 之前 | 现在 |
|---|---|---|
| `transcribe_via_crv.py :: run_crv` | `subprocess.run(capture_output=True, text=True)` | `run_guarded(..., mem_limit_mb, log_path=...)` |
| `transcribe_via_crv.py :: _fallback_to_faster_whisper` | `subprocess.run(...)` 无上限 | `run_guarded(...)` |
| `transcribe_via_crv.py :: transcribe` | 无预算检查 | `budget_check()` 先算账，超预算 exit 4 |
| `transcribe_via_crv.py :: probe_duration_seconds` | 直接 ffmpeg | 护栏内的 ffmpeg（探测也是跑 ffmpeg） |
| `transcribe_via_crv.py :: find_crv_transcript_dir` | 只认 `crv-out-*` 子目录 | 新旧两种布局都认（crv 0.10.x 直接写进 `--out`） |
| `transcribe_via_crv.py :: load_segments_from_crv` | 只认 `audio.json` | `transcript.json` → `audio.json` → srt → txt 都认 |
| `transcribe_via_crv.py :: crv_has_transcript` | 无 | **验产物**：crv exit 0 ≠ 转写成功（坏 ffprobe 会让它静默跳过） |
| `asr_faster_whisper.py :: transcribe_segment` | 整轨一次 STFT（长片必炸） | **窗口化**转写（`--split-seconds`，默认 600 s） |
| `asr_faster_whisper.py :: _install_ceiling` | 无 | 进程内 commit 硬上限 |
| `doc_to_md.py :: antiword` | `text=True` 无 encoding | `encoding="utf-8", errors="replace"` |

## 4 · 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | crv + fallback 都失败 |
| 2 | 参数错误 / 文件不存在 |
| 3 | crv 产物解析失败（已写 ERROR 标注的 transcript.md） |
| **4** | **超出资源预算**（时长超限 / 预估峰值超上限）—— 护栏在启动前拦下，**不是故障** |

## 5 · 反模式

| ❌ | ✅ |
|---|---|
| 「只是探测一下时长，不会有事」 | 探测也是跑 ffmpeg；危险的分配不因为用途轻就变安全 |
| 「先裸跑看看，不行再加护栏」 | 护栏必须在子进程启动前装好，事后加等于没加 |
| 「用采样监控盯着内存就行」 | 分配速度远超采样间隔，20 ms 轮询拦不住 |
| 「上次这么跑没出事」 | 该形态是间歇性的，8 次里炸 1 次 |
| 「text=True 默认就是 UTF-8」 | Windows 上是 GBK；必须显式 encoding + errors |

## 6 · 自检

```bash
# 护栏自测：贪心子进程必须被内核拒绝，机器提交量不出现尖峰
python scripts/memory_guard.py          # MEM_LIMIT_MB 默认 256
# 回归测试
python -m pytest tests/test_memory_guard.py -q
```
