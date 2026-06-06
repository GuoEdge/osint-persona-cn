import { useParams, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { ArrowLeft, Radar, FileText, MessageSquare, BarChart3 } from 'lucide-react';
import ReactECharts from 'echarts-for-react';
import { API_BASE, type DanmakuResult } from '@/store';

export default function VideoAnalysis() {
  const { videoId } = useParams<{ videoId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<DanmakuResult | null>(null);
  const [report, setReport] = useState<string>('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!videoId) return;
    const fetchData = async () => {
      try {
        // 尝试从快捷任务获取结果
        const res = await fetch(`${API_BASE}/api/quick/${videoId}`);
        const json = await res.json();
        if (json.result) {
          setData(json.result);
          // 尝试加载报告
          if (json.result.reportPath) {
            try {
              const reportRes = await fetch(`${API_BASE}/output/${json.result.reportPath.split('/').pop()}`);
              if (reportRes.ok) {
                setReport(await reportRes.text());
              }
            } catch { /* ignore */ }
          }
        }
      } catch (err) {
        console.error('获取视频分析数据失败:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [videoId]);

  if (loading) {
    return (
      <div className="min-h-screen grid-bg flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-2 border-radar-cyan border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="font-mono text-radar-cyan text-sm">加载视频分析...</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen grid-bg flex items-center justify-center">
        <div className="glass rounded-xl p-8 text-center">
          <p className="text-radar-muted font-mono">未找到视频分析数据</p>
          <button onClick={() => navigate('/')} className="mt-4 text-radar-cyan text-sm font-mono hover:underline">
            返回搜索
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen grid-bg">
      {/* 导航 */}
      <nav className="glass border-b border-radar-border sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
          <button onClick={() => navigate(-1)} className="text-radar-muted hover:text-radar-cyan transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <Radar className="w-5 h-5 text-radar-cyan" />
          <span className="font-mono font-bold text-radar-cyan glow-text">视频分析</span>
          <span className="text-radar-muted font-mono text-sm">/</span>
          <span className="text-radar-text font-sans text-sm line-clamp-1">{data.videoTitle}</span>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* 视频信息卡 */}
        <div className="glass rounded-xl p-5 mb-6">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-lg bg-radar-card flex items-center justify-center shrink-0">
              <span className="text-2xl font-bold text-radar-pink">B</span>
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="text-lg text-radar-text font-sans mb-1 line-clamp-1">{data.videoTitle}</h2>
              <div className="flex items-center gap-4 text-xs text-radar-muted font-mono">
                <span>{data.totalDanmaku} 条弹幕</span>
                <span>
                  情感分:{' '}
                  <span className="text-radar-cyan">
                    {((data.sentiment.positive / (data.sentiment.positive + data.sentiment.neutral + data.sentiment.negative)) * 100).toFixed(1)}%
                  </span>{' '}
                  正向
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* 情感分析 */}
          <div className="glass rounded-xl p-5">
            <h3 className="font-mono text-sm text-radar-cyan mb-4 flex items-center gap-2">
              <MessageSquare className="w-4 h-4" />
              弹幕情感分析
            </h3>
            <ReactECharts
              option={{
                tooltip: { trigger: 'item' },
                series: [{
                  type: 'pie',
                  radius: ['35%', '65%'],
                  itemStyle: { borderRadius: 6, borderColor: '#111827', borderWidth: 2 },
                  label: { color: '#e2e8f0', fontSize: 12, formatter: '{b}\n{c} ({d}%)' },
                  data: [
                    { name: '正向', value: data.sentiment.positive, itemStyle: { color: '#10b981' } },
                    { name: '中性', value: data.sentiment.neutral, itemStyle: { color: '#f59e0b' } },
                    { name: '负向', value: data.sentiment.negative, itemStyle: { color: '#ef4444' } },
                  ],
                }],
              }}
              style={{ height: 280 }}
            />
          </div>

          {/* 高频词 */}
          <div className="glass rounded-xl p-5">
            <h3 className="font-mono text-sm text-radar-cyan mb-4 flex items-center gap-2">
              <BarChart3 className="w-4 h-4" />
              高频词 TOP 20
            </h3>
            <ReactECharts
              option={{
                tooltip: { trigger: 'axis' },
                xAxis: {
                  type: 'value',
                  axisLabel: { color: '#64748b', fontSize: 10 },
                  splitLine: { lineStyle: { color: '#1e293b' } },
                },
                yAxis: {
                  type: 'category',
                  data: data.topWords.slice(0, 20).map((w) => w.word).reverse(),
                  axisLabel: { color: '#e2e8f0', fontSize: 11, fontFamily: 'Noto Sans SC' },
                },
                series: [{
                  type: 'bar',
                  data: data.topWords.slice(0, 20).map((w) => w.count).reverse(),
                  itemStyle: {
                    color: {
                      type: 'linear',
                      x: 0, y: 0, x2: 1, y2: 0,
                      colorStops: [
                        { offset: 0, color: '#00f0ff' },
                        { offset: 1, color: '#ff6b35' },
                      ],
                    },
                    borderRadius: [0, 4, 4, 0],
                  },
                  barWidth: 14,
                }],
                grid: { left: 80, right: 20, top: 10, bottom: 20 },
              }}
              style={{ height: 280 }}
            />
          </div>
        </div>

        {/* 词云图 */}
        {data.wordcloudPath && (
          <div className="glass rounded-xl p-5 mb-6">
            <h3 className="font-mono text-sm text-radar-cyan mb-4">弹幕词云</h3>
            <img
              src={`${API_BASE}/output/${data.wordcloudPath.split('/').pop()}`}
              alt="词云"
              className="max-w-full rounded-lg mx-auto"
              style={{ maxHeight: 400 }}
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
          </div>
        )}

        {/* 舆情报告 */}
        {report && (
          <div className="glass rounded-xl p-5 mb-6">
            <h3 className="font-mono text-sm text-radar-cyan mb-4 flex items-center gap-2">
              <FileText className="w-4 h-4" />
              舆情分析报告
            </h3>
            <div className="prose prose-invert prose-sm max-w-none">
              {report.split('\n').map((line, i) => {
                if (line.startsWith('# ')) return <h1 key={i} className="text-lg text-radar-text font-sans font-bold mt-4 mb-2">{line.slice(2)}</h1>;
                if (line.startsWith('## ')) return <h2 key={i} className="text-base text-radar-cyan font-sans font-bold mt-4 mb-2">{line.slice(3)}</h2>;
                if (line.startsWith('### ')) return <h3 key={i} className="text-sm text-radar-orange font-sans font-bold mt-3 mb-1">{line.slice(4)}</h3>;
                if (line.startsWith('- ')) return <li key={i} className="text-sm text-radar-text ml-4">{line.slice(2)}</li>;
                if (line.startsWith('**')) {
                  const text = line.replace(/\*\*/g, '');
                  return <p key={i} className="text-sm text-radar-cyan font-bold">{text}</p>;
                }
                if (line.trim()) return <p key={i} className="text-sm text-radar-text/80">{line}</p>;
                return null;
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
