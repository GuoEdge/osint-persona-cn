import { create } from 'zustand';

export type Platform = 'zhihu' | 'bilibili' | 'weibo' | 'tieba' | 'xhs' | 'douyin' | 'kuaishou';

export interface PlatformStatus {
  platform: Platform;
  status: 'pending' | 'running' | 'completed' | 'error';
  progress: number;
  resultCount: number;
  message: string;
}

export interface DanmakuResult {
  videoUrl: string;
  videoTitle: string;
  totalDanmaku: number;
  sentiment: { positive: number; neutral: number; negative: number };
  topWords: { word: string; count: number }[];
  wordcloudPath: string;
  reportPath: string;
}

export interface TranscriptResult {
  videoUrl: string;
  videoTitle: string;
  transcript: string;
}

export interface ContentItem {
  id: string;
  title: string;
  content: string;
  url: string;
  author: string;
  publishTime: string;
  commentCount: number;
  comments: { content: string; author: string; time: string; sentiment: string }[];
}

export interface SearchResult {
  queryId: string;
  keyword: string;
  queryTime: string;
  platforms: Record<string, { items: ContentItem[] }>;
  danmaku: DanmakuResult[];
  transcripts: TranscriptResult[];
}

export interface HistoryItem {
  queryId: string;
  keyword: string;
  queryTime: string;
  platformCount: number;
  totalResults: number;
}

interface AppState {
  // 搜索
  keyword: string;
  setKeyword: (k: string) => void;
  selectedPlatforms: Platform[];
  togglePlatform: (p: Platform) => void;
  days: number;
  setDays: (d: number) => void;

  // 搜索状态
  isSearching: boolean;
  queryId: string | null;
  platformStatuses: PlatformStatus[];
  searchResult: SearchResult | null;

  // WebSocket
  wsConnected: boolean;

  // 搜索历史
  history: HistoryItem[];

  // Actions
  startSearch: () => void;
  resetSearch: () => void;
  updatePlatformStatus: (platform: string, status: Partial<PlatformStatus>) => void;
  setSearchResult: (result: SearchResult) => void;
  setWsConnected: (connected: boolean) => void;
  addHistory: (item: HistoryItem) => void;
  loadHistory: () => void;
}

const ALL_PLATFORMS: Platform[] = ['zhihu', 'bilibili', 'weibo', 'tieba', 'xhs', 'douyin', 'kuaishou'];

const API_BASE = '';

export const useStore = create<AppState>((set, get) => ({
  keyword: '',
  setKeyword: (k) => set({ keyword: k }),
  selectedPlatforms: ['zhihu', 'bilibili', 'weibo'],
  togglePlatform: (p) =>
    set((state) => {
      const exists = state.selectedPlatforms.includes(p);
      return {
        selectedPlatforms: exists
          ? state.selectedPlatforms.filter((x) => x !== p)
          : [...state.selectedPlatforms, p],
      };
    }),
  days: 7,
  setDays: (d) => set({ days: d }),

  isSearching: false,
  queryId: null,
  platformStatuses: ALL_PLATFORMS.map((p) => ({
    platform: p,
    status: 'pending' as const,
    progress: 0,
    resultCount: 0,
    message: '',
  })),
  searchResult: null,
  wsConnected: false,
  history: [],

  startSearch: async () => {
    const { keyword, selectedPlatforms, days } = get();
    if (!keyword.trim()) return;

    set({ isSearching: true, queryId: null, searchResult: null });
    set({
      platformStatuses: ALL_PLATFORMS.map((p) => ({
        platform: p,
        status: selectedPlatforms.includes(p) ? 'pending' : ('pending' as const),
        progress: 0,
        resultCount: 0,
        message: '',
      })),
    });

    try {
      const res = await fetch(`${API_BASE}/api/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          keyword,
          platforms: selectedPlatforms,
          days,
          max_notes: 20,
          max_comments: 20,
        }),
      });
      const data = await res.json();
      const qid = data.query_id;
      set({ queryId: qid });

      // 连接 WebSocket
      const ws = new WebSocket(`ws://localhost:8000/ws/search/${qid}`);
      ws.onopen = () => set({ wsConnected: true });
      ws.onclose = () => set({ wsConnected: false });
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'progress') {
          get().updatePlatformStatus(msg.platform, {
            status: msg.status,
            progress: msg.progress,
            message: msg.message,
          });
        } else if (msg.type === 'complete') {
          set({ isSearching: false });
          ws.close();
        }
      };
    } catch (err) {
      console.error('搜索失败:', err);
      set({ isSearching: false });
    }
  },

  resetSearch: () =>
    set({
      isSearching: false,
      queryId: null,
      searchResult: null,
      platformStatuses: ALL_PLATFORMS.map((p) => ({
        platform: p,
        status: 'pending' as const,
        progress: 0,
        resultCount: 0,
        message: '',
      })),
    }),

  updatePlatformStatus: (platform, status) =>
    set((state) => ({
      platformStatuses: state.platformStatuses.map((ps) =>
        ps.platform === platform ? { ...ps, ...status } : ps
      ),
    })),

  setSearchResult: (result) => set({ searchResult: result, isSearching: false }),

  setWsConnected: (connected) => set({ wsConnected: connected }),

  addHistory: (item) => set((state) => ({ history: [item, ...state.history].slice(0, 20) })),

  loadHistory: async () => {
    try {
      const res = await fetch(`${API_BASE}/api/history`);
      const data = await res.json();
      set({ history: data.queries || [] });
    } catch {
      // 静默失败
    }
  },
}));

export { ALL_PLATFORMS, API_BASE };
