import { useParams, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { Radar, ArrowLeft, ExternalLink, MessageSquare, Video, TrendingUp } from 'lucide-react';
import ReactECharts from 'echarts-for-react';
import { API_BASE, type DanmakuResult, type ContentItem } from '@/store';

const PLATFORM_META: Record<string, { label: string; icon: string; color: string }> = {
  zhihu: { label: '知乎', icon: '知', color: '#0084ff' },
  bilibili: { label: 'B站', icon: 'B', color: '#fb7299' },
  weibo: { label: '微博', icon: '微', color: '#e6162d' },
  tieba: { label: '贴吧', icon: '贴', color: '#4e6ef2' },
  xhs: { label: '小红书', icon: '书', color: '#fe2c55' },
  douyin: { label: '抖音', icon: '抖', color: '#00f2ea' },
  kuaishou: { label: '快手', icon: '快', color: '#ff4906' },
};

interface DashboardData {
  queryId: string;
  keyword: string;
  queryTime: string;
  platforms: Record<string, { items: ContentItem[] }>;
  danmaku: DanmakuResult[];
}

export default function Dashboard() {
  const { queryId } = useParams<{ queryId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'sentiment' | 'danmaku'>('overview');

  useEffect(() => {
    if (!queryId) return;
    const fetchData = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/search/${queryId}/results`);
        const json = await res.json();
        setData(json);
      } catch (err) {
        console.error('获取结果失败:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [queryId]);

  if (loading) {
    return (
      <div className="min-h-screen grid-bg flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-2 border-radar-cyan border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="font-mono text-radar-cyan text-sm">加载情报数据...</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen grid-bg flex items-center justify-center">
        <div className="glass rounded-xl p-8 text-center">
          <p className="text-radar-muted font-mono">未找到查询结果</p>
          <button onClick={() => navigate('/')} className="mt-4 text-radar-cyan text-sm font-mono hover:underline">
            返回搜索
          </button>
        </div>
      </div>
    );
  }

  // 汇总情感数据
  const totalSentiment = data.danmaku.reduce(
    (acc, d) => ({
      positive: acc.positive + d.sentiment.positive,
      neutral: acc.neutral + d.sentiment.neutral,
      negative: acc.negative + d.sentiment.negative,
    }),
    { positive: 0, neutral: 0, negative: 0 }
  );

  // 汇总热词
  const allTopWords: Record<string, number> = {};
  data.danmaku.forEach((d) => {
    d.topWords.forEach((w) => {
      allTopWords[w.word] = (allTopWords[w.word] || 0) + w.count;
    });
  });
  const sortedWords = Object.entries(allTopWords)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 30);

  // 各平台内容数量
  const platformCounts = Object.entries(data.platforms || {}).map(([p, d]) => ({
    platform: p,
    count: d.items?.length || 0,
  }));

  return (
    <div className="min-h-screen grid-bg">
      {/* 导航 */}
      <nav className="glass border-b border-radar-border sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate('/')} className="text-radar-muted hover:text-radar-cyan transition-colors">
              <ArrowLeft className="w-5 h-5" />
            </button>
            <Radar className="w-5 h-5 text-radar-cyan" />
            <span className="font-mono font-bold text-radar-cyan glow-text">OSINT RADAR</span>
            <span className="text-radar-muted font-mono text-sm">/</span>
            <span className="text-radar-text font-sans">{data.keyword}</span>
          </div>
          <span className="text-xs text-radar-muted font-mono">{data.queryTime}</span>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* 标签页 */}
        <div className="flex gap-2 mb-6">
          {[
            { key: 'overview', label: '内容总览', icon: <TrendingUp className="w-4 h-4" /> },
            { key: 'sentiment', label: '情感分析', icon: <MessageSquare className="w-4 h-4" /> },
            { key: 'danmaku', label: '弹幕分析', icon: <Video className="w-4 h-4" /> },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as typeof activeTab)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-mono text-sm transition-all ${
                activeTab === tab.key
                  ? 'glass-cyan text-radar-cyan shadow-glow-sm'
                  : 'text-radar-muted hover:text-radar-text'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* 内容总览 */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* 统计卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard label="采集平台" value={String(platformCounts.length)} sub="个平台" />
              <StatCard label="内容总数" value={String(platformCounts.reduce((s, p) => s + p.count, 0))} sub="条" />
              <StatCard label="弹幕分析" value={String(data.danmaku.length)} sub="个视频" />
              <StatCard
                label="情感倾向"
                value={
                  totalSentiment.positive > totalSentiment.negative ? '正向' : totalSentiment.positive < totalSentiment.negative ? '负向' : '中性'
                }
                sub="主导"
              />
            </div>

            {/* 平台内容分布 */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="glass rounded-xl p-5">
                <h3 className="font-mono text-sm text-radar-cyan mb-4">平台内容分布</h3>
                <ReactECharts
                  option={{
                    tooltip: { trigger: 'item' },
                    series: [{
                      type: 'pie',
                      radius: ['40%', '70%'],
                      itemStyle: { borderRadius: 6, borderColor: '#111827', borderWidth: 2 },
                      label: { color: '#e2e8f0', fontSize: 11, fontFamily: 'JetBrains Mono' },
                      data: platformCounts.map((p) => ({
                        name: PLATFORM_META[p.platform]?.label || p.platform,
                        value: p.count,
                        itemStyle: { color: PLATFORM_META[p.platform]?.color || '#64748b' },
                      })),
                    }],
                  }}
                  style={{ height: 250 }}
                />
              </div>

              {/* 热词 */}
              <div className="glass rounded-xl p-5">
                <h3 className="font-mono text-sm text-radar-cyan mb-4">热词 TOP 15</h3>
                <div className="space-y-2">
                  {sortedWords.slice(0, 15).map(([word, count], i) => (
                    <div key={word} className="flex items-center gap-3">
                      <span className="w-5 text-right text-xs font-mono text-radar-muted">{i + 1}</span>
                      <span className="text-sm text-radar-text font-sans flex-1">{word}</span>
                      <div className="w-32 bg-radar-border rounded-full h-2">
                        <div
                          className="h-2 rounded-full"
                          style={{
                            width: `${(count / (sortedWords[0]?.[1] || 1)) * 100}%`,
                            background: `linear-gradient(90deg, #00f0ff, #ff6b35)`,
                          }}
                        />
                      </div>
                      <span className="text-xs font-mono text-radar-muted w-8 text-right">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* 各平台内容列表 */}
            {Object.entries(data.platforms || {}).map(([platform, pData]) => (
              <div key={platform}>
                <h3 className="font-mono text-sm mb-3 flex items-center gap-2">
                  <span style={{ color: PLATFORM_META[platform]?.color }}>
                    {PLATFORM_META[platform]?.icon}
                  </span>
                  <span className="text-radar-text">{PLATFORM_META[platform]?.label || platform}</span>
                  <span className="text-radar-muted">({pData.items?.length || 0}条)</span>
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {(pData.items || []).slice(0, 6).map((item: ContentItem) => (
                    <div key={item.id} className="glass rounded-lg p-4 hover:border-radar-cyan/30 transition-all">
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <h4 className="text-sm text-radar-text font-sans line-clamp-2">{item.title}</h4>
                        {item.url && (
                          <a href={item.url} target="_blank" rel="noopener noreferrer" className="text-radar-cyan shrink-0">
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </div>
                      <p className="text-xs text-radar-muted line-clamp-2 mb-2">{item.content}</p>
                      <div className="flex items-center gap-3 text-[10px] text-radar-muted font-mono">
                        <span>{item.author}</span>
                        <span>{item.publishTime}</span>
                        <span>{item.commentCount} 评论</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 情感分析 */}
        {activeTab === 'sentiment' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="glass rounded-xl p-5">
                <h3 className="font-mono text-sm text-radar-cyan mb-4">整体情感分布</h3>
                <ReactECharts
                  option={{
                    tooltip: { trigger: 'item' },
                    series: [{
                      type: 'pie',
                      radius: ['35%', '65%'],
                      itemStyle: { borderRadius: 6, borderColor: '#111827', borderWidth: 2 },
                      label: { color: '#e2e8f0', fontSize: 12, formatter: '{b}: {c} ({d}%)' },
                      data: [
                        { name: '正向', value: totalSentiment.positive, itemStyle: { color: '#10b981' } },
                        { name: '中性', value: totalSentiment.neutral, itemStyle: { color: '#f59e0b' } },
                        { name: '负向', value: totalSentiment.negative, itemStyle: { color: '#ef4444' } },
                      ],
                    }],
                  }}
                  style={{ height: 300 }}
                />
              </div>

              <div className="glass rounded-xl p-5">
                <h3 className="font-mono text-sm text-radar-cyan mb-4">各视频弹幕情感对比</h3>
                <ReactECharts
                  option={{
                    tooltip: { trigger: 'axis' },
                    legend: { textStyle: { color: '#64748b', fontSize: 11 }, top: 0 },
                    xAxis: {
                      type: 'category',
                      data: data.danmaku.map((d, i) => `视频${i + 1}`),
                      axisLabel: { color: '#64748b', fontSize: 10 },
                    },
                    yAxis: { axisLabel: { color: '#64748b', fontSize: 10 }, splitLine: { lineStyle: { color: '#1e293b' } } },
                    series: [
                      { name: '正向', type: 'bar', stack: 'total', data: data.danmaku.map((d) => d.sentiment.positive), itemStyle: { color: '#10b981' } },
                      { name: '中性', type: 'bar', stack: 'total', data: data.danmaku.map((d) => d.sentiment.neutral), itemStyle: { color: '#f59e0b' } },
                      { name: '负向', type: 'bar', stack: 'total', data: data.danmaku.map((d) => d.sentiment.negative), itemStyle: { color: '#ef4444' } },
                    ],
                  }}
                  style={{ height: 300 }}
                />
              </div>
            </div>
          </div>
        )}

        {/* 弹幕分析 */}
        {activeTab === 'danmaku' && (
          <div className="space-y-6">
            {data.danmaku.length === 0 ? (
              <div className="glass rounded-xl p-8 text-center">
                <p className="text-radar-muted font-mono">暂无弹幕分析数据</p>
              </div>
            ) : (
              data.danmaku.map((dm, i) => (
                <div key={i} className="glass rounded-xl p-5">
                  <div className="flex items-center gap-3 mb-4">
                    <span className="text-radar-pink font-bold font-mono">B</span>
                    <h3 className="text-sm text-radar-text font-sans flex-1 line-clamp-1">{dm.videoTitle}</h3>
                    <span className="text-xs text-radar-muted font-mono">{dm.totalDanmaku} 条弹幕</span>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {/* 情感饼图 */}
                    <ReactECharts
                      option={{
                        tooltip: { trigger: 'item' },
                        series: [{
                          type: 'pie',
                          radius: ['30%', '60%'],
                          label: { color: '#e2e8f0', fontSize: 11, formatter: '{b}\n{d}%' },
                          data: [
                            { name: '正向', value: dm.sentiment.positive, itemStyle: { color: '#10b981' } },
                            { name: '中性', value: dm.sentiment.neutral, itemStyle: { color: '#f59e0b' } },
                            { name: '负向', value: dm.sentiment.negative, itemStyle: { color: '#ef4444' } },
                          ],
                        }],
                      }}
                      style={{ height: 200 }}
                    />

                    {/* 热词 */}
                    <div>
                      <h4 className="text-xs font-mono text-radar-muted mb-2">高频词</h4>
                      <div className="flex flex-wrap gap-1.5">
                        {dm.topWords.slice(0, 20).map((w) => (
                          <span
                            key={w.word}
                            className="px-2 py-0.5 rounded text-xs font-mono"
                            style={{
                              backgroundColor: `rgba(0, 240, 255, ${Math.min(w.count / (dm.topWords[0]?.count || 1), 1) * 0.3})`,
                              color: '#00f0ff',
                            }}
                          >
                            {w.word}({w.count})
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* 词云图 */}
                  {dm.wordcloudPath && (
                    <div className="mt-4">
                      <img
                        src={`${API_BASE}/output/${dm.wordcloudPath.split('/').pop()}`}
                        alt="词云"
                        className="max-w-full rounded-lg"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                    </div>
                  )}

                  {/* 查看详情 */}
                  <button
                    onClick={() => navigate(`/video/${queryId}-${i}`)}
                    className="mt-3 text-xs font-mono text-radar-cyan hover:underline"
                  >
                    查看完整舆情报告 →
                  </button>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="glass rounded-xl p-4 text-center">
      <p className="text-2xl font-mono font-bold text-radar-cyan glow-text">{value}</p>
      <p className="text-xs text-radar-muted font-mono mt-1">{label} <span className="text-radar-text">{sub}</span></p>
    </div>
  );
}
