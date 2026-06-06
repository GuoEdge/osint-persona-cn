import { Search, Radar, Zap, Clock, Loader2, CheckCircle2, XCircle, AlertCircle } from 'lucide-react';
import { useStore, ALL_PLATFORMS, API_BASE } from '@/store';
import { useNavigate } from 'react-router-dom';
import { useEffect } from 'react';

const PLATFORM_META: Record<string, { label: string; icon: string; color: string }> = {
  zhihu: { label: '知乎', icon: '知', color: '#0084ff' },
  bilibili: { label: 'B站', icon: 'B', color: '#fb7299' },
  weibo: { label: '微博', icon: '微', color: '#e6162d' },
  tieba: { label: '贴吧', icon: '贴', color: '#4e6ef2' },
  xhs: { label: '小红书', icon: '书', color: '#fe2c55' },
  douyin: { label: '抖音', icon: '抖', color: '#00f2ea' },
  kuaishou: { label: '快手', icon: '快', color: '#ff4906' },
};

export default function Home() {
  const {
    keyword, setKeyword,
    selectedPlatforms, togglePlatform,
    days, setDays,
    isSearching, queryId, platformStatuses,
    wsConnected,
    startSearch, loadHistory, history,
  } = useStore();
  const navigate = useNavigate();

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // 搜索完成后跳转仪表盘
  useEffect(() => {
    if (queryId && !isSearching) {
      const allDone = platformStatuses
        .filter((ps) => selectedPlatforms.includes(ps.platform))
        .every((ps) => ps.status === 'completed' || ps.status === 'error');
      if (allDone) {
        navigate(`/dashboard/${queryId}`);
      }
    }
  }, [queryId, isSearching, platformStatuses, selectedPlatforms, navigate]);

  const handleQuickDanmaku = async () => {
    const url = prompt('请输入B站视频链接:');
    if (!url) return;
    try {
      const res = await fetch(`${API_BASE}/api/quick/danmaku`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (data.task_id) {
        navigate(`/video/${data.task_id}`);
      }
    } catch (err) {
      console.error('快捷弹幕分析失败:', err);
    }
  };

  return (
    <div className="min-h-screen grid-bg">
      {/* 顶部导航 */}
      <nav className="glass border-b border-radar-border sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Radar className="w-6 h-6 text-radar-cyan" />
            <span className="font-mono font-bold text-lg text-radar-cyan glow-text">OSINT RADAR</span>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={handleQuickDanmaku}
              className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono text-radar-cyan border border-radar-cyan/30 rounded hover:bg-radar-cyan/10 transition-all"
            >
              <Zap className="w-3.5 h-3.5" />
              快捷弹幕分析
            </button>
            {wsConnected && (
              <span className="flex items-center gap-1.5 text-xs text-radar-green font-mono">
                <span className="w-2 h-2 rounded-full bg-radar-green animate-pulse" />
                WS
              </span>
            )}
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-12">
        {/* 搜索区域 */}
        <div className="text-center mb-12">
          <h1 className="font-mono text-5xl font-bold text-radar-text mb-3">
            <span className="text-radar-cyan glow-text">情报</span>搜索中心
          </h1>
          <p className="text-radar-muted text-sm font-mono">
            多平台实时采集 · 视频内容识别 · 弹幕情感分析 · 一键生成报告
          </p>
        </div>

        {/* 搜索框 */}
        <div className="max-w-3xl mx-auto mb-8">
          <div className="glass-cyan rounded-xl p-1 glow-border">
            <div className="flex items-center gap-2">
              <Search className="w-5 h-5 text-radar-cyan ml-4 shrink-0" />
              <input
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && startSearch()}
                placeholder="输入关键词，如：DeepSeek 评测、Kimi vs GLM 对比..."
                className="flex-1 bg-transparent text-radar-text text-lg py-3 px-2 outline-none placeholder:text-radar-muted/50 font-sans"
              />
              <button
                onClick={startSearch}
                disabled={isSearching || !keyword.trim()}
                className="px-6 py-2.5 bg-radar-cyan/20 text-radar-cyan font-mono font-bold rounded-lg hover:bg-radar-cyan/30 transition-all disabled:opacity-30 disabled:cursor-not-allowed mr-1"
              >
                {isSearching ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  '搜索'
                )}
              </button>
            </div>
          </div>
        </div>

        {/* 平台选择 */}
        <div className="max-w-3xl mx-auto mb-8">
          <div className="flex items-center justify-center gap-3 flex-wrap">
            {ALL_PLATFORMS.map((p) => {
              const meta = PLATFORM_META[p];
              const selected = selectedPlatforms.includes(p);
              return (
                <button
                  key={p}
                  onClick={() => togglePlatform(p)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg font-mono text-sm transition-all ${
                    selected
                      ? 'glass-cyan text-radar-cyan shadow-glow-sm'
                      : 'glass text-radar-muted hover:text-radar-text'
                  }`}
                >
                  <span
                    className="w-6 h-6 rounded flex items-center justify-center text-xs font-bold"
                    style={{ backgroundColor: selected ? meta.color + '33' : 'transparent', color: meta.color }}
                  >
                    {meta.icon}
                  </span>
                  {meta.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* 时间范围 */}
        <div className="max-w-3xl mx-auto mb-12 flex items-center justify-center gap-4">
          <Clock className="w-4 h-4 text-radar-muted" />
          <span className="text-radar-muted text-sm font-mono">时间范围:</span>
          {[1, 3, 7, 30].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1 rounded text-xs font-mono transition-all ${
                days === d
                  ? 'bg-radar-orange/20 text-radar-orange'
                  : 'text-radar-muted hover:text-radar-text'
              }`}
            >
              {d === 1 ? '24小时' : `${d}天`}
            </button>
          ))}
        </div>

        {/* 采集状态 */}
        {isSearching && (
          <div className="max-w-3xl mx-auto mb-12">
            <div className="glass rounded-xl p-6 scan-bg">
              <h3 className="font-mono text-sm text-radar-cyan mb-4 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                正在采集情报...
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {platformStatuses
                  .filter((ps) => selectedPlatforms.includes(ps.platform))
                  .map((ps) => {
                    const meta = PLATFORM_META[ps.platform];
                    return (
                      <div key={ps.platform} className="glass rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-xs font-bold" style={{ color: meta.color }}>
                            {meta.icon}
                          </span>
                          <span className="text-xs font-mono text-radar-text">{meta.label}</span>
                          <StatusIcon status={ps.status} />
                        </div>
                        <div className="w-full bg-radar-border rounded-full h-1.5">
                          <div
                            className="h-1.5 rounded-full transition-all duration-500"
                            style={{
                              width: `${ps.progress}%`,
                              backgroundColor: ps.status === 'error' ? '#ef4444' : '#00f0ff',
                            }}
                          />
                        </div>
                        <p className="text-[10px] text-radar-muted mt-1 truncate">{ps.message}</p>
                      </div>
                    );
                  })}
              </div>
            </div>
          </div>
        )}

        {/* 搜索历史 */}
        {history.length > 0 && (
          <div className="max-w-3xl mx-auto">
            <h3 className="font-mono text-sm text-radar-muted mb-3 flex items-center gap-2">
              <Clock className="w-3.5 h-3.5" />
              最近搜索
            </h3>
            <div className="space-y-2">
              {history.slice(0, 5).map((item) => (
                <button
                  key={item.query_id}
                  onClick={() => navigate(`/dashboard/${item.query_id}`)}
                  className="w-full glass rounded-lg p-3 flex items-center justify-between hover:border-radar-cyan/30 transition-all text-left"
                >
                  <div>
                    <span className="text-sm text-radar-text font-sans">{item.keyword}</span>
                    <span className="text-xs text-radar-muted ml-3 font-mono">
                      {item.platformCount} 个平台 · {item.totalResults} 条结果
                    </span>
                  </div>
                  <span className="text-xs text-radar-muted font-mono">{item.query_time}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'running':
      return <Loader2 className="w-3.5 h-3.5 text-radar-cyan animate-spin ml-auto" />;
    case 'completed':
      return <CheckCircle2 className="w-3.5 h-3.5 text-radar-green ml-auto" />;
    case 'error':
      return <XCircle className="w-3.5 h-3.5 text-radar-red ml-auto" />;
    default:
      return <AlertCircle className="w-3.5 h-3.5 text-radar-muted ml-auto" />;
  }
}
