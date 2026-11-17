import React, { useState, useMemo, useEffect } from 'react';
import {
  Moon,
  Calendar,
  Sprout,
  Zap,
  Footprints,
  Droplets,
  ClipboardList,
  Flame,
  Leaf,
  BatteryCharging,
  Sparkles,
  Target,
  Send,
  RotateCcw,
  Search,
  ArrowRight,
  ArrowLeft,
  ChevronUp,
  ChevronDown,
  X,
  Maximize2
} from 'lucide-react';
import './App.css';

// Единый монохромный цвет для иконок
const ICON_COLOR = '#f9f9f9';
const runtimeConfig = typeof window !== 'undefined' ? window : {};
const API_BASE = String(runtimeConfig.SAIN_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
const INITIAL_USER_ID = runtimeConfig.SAIN_USER_ID || '';

const formatDate = (value) => {
  if (!value) return 'Дата не указана';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
};

const formatHours = (hours) => {
  if (typeof hours !== 'number' || !Number.isFinite(hours)) return 'Нет данных';
  const totalMinutes = Math.round(hours * 60);
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  return m ? `${h}ч ${m}м` : `${h}ч`;
};

// -------------------------------------------------------------
// РЕЖИМЫ КОНТЕКСТА (Паттерны 90 дней — живут в окне Ассистента)
// -------------------------------------------------------------
const SCENARIOS = [
  {
    id: 'flight',
    title: 'Перед перелётом',
    // Маленькие виджеты (календарь и вода) идут парой, чтобы занять одну общую строку
    widgetIds: ['calendar_brief', 'water_tracker', 'sleep_card', 'day_plan']
  },
  {
    id: 'restart',
    title: 'После срыва привычки',
    // Маленькие виджеты (восстановление и стрик) идут парой в одну строку
    widgetIds: ['recovery_tip', 'habit_streak', 'restart_card', 'workout_suggest']
  },
  {
    id: 'peak',
    title: 'Пик продуктивности',
    // Маленькие виджеты (шаги и цель) идут парой в одну строку
    widgetIds: ['steps_ring', 'goal_progress', 'energy_forecast', 'day_plan']
  }
];

// -------------------------------------------------------------
// БЫСТРЫЕ ВОПРОСЫ К АССИСТЕНТУ (ЛАКОНИЧНЫЕ ОТВЕТЫ ИЗ ПАМЯТИ 90 ДНЕЙ)
// -------------------------------------------------------------
const SMART_PRESETS = [
  { q: '🌙 Что известно о моём сне?' },
  { q: '📊 Какие закономерности есть в моей истории?' },
  { q: '🏃 Какая активность была недавно?' },
  { q: '🎯 Что ты знаешь о моей цели?' }
];

export default function App() {
  const [view, setView] = useState('morning'); // 'morning' | 'chat' | 'catalog'
  const [activeModeId, setActiveModeId] = useState('flight');
  const [activeCategory, setActiveCategory] = useState('all');
  const [morningWidgetIds, setMorningWidgetIds] = useState(SCENARIOS[0].widgetIds);
  const [widgetConfigs, setWidgetConfigs] = useState({});
  const [savedModes, setSavedModes] = useState([]);
  const [dashboardLoaded, setDashboardLoaded] = useState(false);
  const [users, setUsers] = useState([]);
  const [userRefreshKey, setUserRefreshKey] = useState(0);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [userSummary, setUserSummary] = useState(null);
  const [apiStatus, setApiStatus] = useState('connecting');
  const [apiError, setApiError] = useState('');
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);
  const [currentTime, setCurrentTime] = useState(() => new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }));
  const [isEditingDashboard, setIsEditingDashboard] = useState(false);
  const [selectedWidgetId, setSelectedWidgetId] = useState(null);
  const [isSending, setIsSending] = useState(false);
  const allWidgetIds = [
    'sleep_card', 'calendar_brief', 'restart_card', 'workout_suggest',
    'steps_ring', 'water_tracker', 'day_plan', 'habit_streak',
    'recovery_tip', 'energy_forecast', 'evening_reflect', 'goal_progress'
  ];

  // Интерактивные данные
  const [quickInput, setQuickInput] = useState('');

  // Чат с ассистентом
  const [messages, setMessages] = useState([
    {
      sender: 'agent',
      text: 'Я SAIN. Могу ответить на вопросы и настроить твой утренний экран. Чем займёмся?'
    }
  ]);
  const [chatInput, setChatInput] = useState('');

  // Связываемся с backend и загружаем список пользователей, появившихся через /run.
  useEffect(() => {
    let cancelled = false;
    const loadUsers = async () => {
      try {
        const healthResponse = await fetch(`${API_BASE}/health`);
        if (!healthResponse.ok) throw new Error(`Backend health: HTTP ${healthResponse.status}`);
        const usersResponse = await fetch(`${API_BASE}/api/sain/users`);
        if (!usersResponse.ok) throw new Error(`Users API: HTTP ${usersResponse.status}`);
        const data = await usersResponse.json();
        const loadedUsers = Array.isArray(data.users) ? data.users : [];
        if (cancelled) return;
        setUsers(loadedUsers);
        setApiStatus('connected');
        const preferred = loadedUsers.find((user) =>
          user.user_id === INITIAL_USER_ID || user.external_id === INITIAL_USER_ID
        );
        setSelectedUserId(preferred?.user_id || loadedUsers[0]?.user_id || '');
        if (!loadedUsers.length) {
          setApiError('Backend подключён, но пользователей пока нет. Данные появятся после получения набора от организаторов через /run.');
          setDashboardLoaded(true);
        }
      } catch (error) {
        if (cancelled) return;
        console.error('Не удалось подключиться к backend SAIN:', error);
        setApiStatus('offline');
        setApiError('Не удалось подключиться к backend. Проверь, что сервер запущен и доступен по адресу API.');
        setDashboardLoaded(true);
      }
    };
    loadUsers();
    return () => { cancelled = true; };
  }, []);

  // Для выбранного пользователя загружаем сохранённый экран и фактические метрики.
  useEffect(() => {
    if (!selectedUserId) return undefined;
    let cancelled = false;
    setDashboardLoaded(false);
    setIsLoadingSummary(true);
    setApiError('');
    setUserSummary(null);

    const loadSelectedUser = async () => {
      try {
        const [stateResponse, summaryResponse] = await Promise.all([
          fetch(`${API_BASE}/api/sain/state/${encodeURIComponent(selectedUserId)}`),
          fetch(`${API_BASE}/api/sain/users/${encodeURIComponent(selectedUserId)}/summary`)
        ]);
        if (!stateResponse.ok) throw new Error(`State API: HTTP ${stateResponse.status}`);
        if (!summaryResponse.ok) throw new Error(`Summary API: HTTP ${summaryResponse.status}`);
        const [stateData, summaryData] = await Promise.all([
          stateResponse.json(), summaryResponse.json()
        ]);
        if (cancelled) return;
        setMorningWidgetIds(Array.isArray(stateData.widget_ids) ? stateData.widget_ids : []);
        setWidgetConfigs(stateData.widget_configs && typeof stateData.widget_configs === 'object' ? stateData.widget_configs : {});
        setSavedModes(Array.isArray(stateData.modes) ? stateData.modes : []);
        setActiveModeId(stateData.active_mode_id || '');
        setUserSummary(summaryData);
      } catch (error) {
        if (!cancelled) {
          console.error('Не удалось загрузить данные выбранного пользователя:', error);
          setApiError('Не удалось загрузить профиль и историю выбранного пользователя.');
        }
      } finally {
        if (!cancelled) {
          setDashboardLoaded(true);
          setIsLoadingSummary(false);
        }
      }
    };
    loadSelectedUser();
    return () => { cancelled = true; };
  }, [selectedUserId, userRefreshKey]);

  // Обновляем часы в шапке без фиксированного демонстрационного времени.
  useEffect(() => {
    const updateTime = () => setCurrentTime(new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }));
    updateTime();
    const intervalId = window.setInterval(updateTime, 60_000);
    return () => window.clearInterval(intervalId);
  }, []);

  const handleUserChange = (event) => {
    const nextUserId = event.target.value;
    if (nextUserId === selectedUserId) return;
    setMessages([{ sender: 'agent', text: 'Я SAIN. Теперь работаю с данными выбранного пользователя.' }]);
    setSelectedUserId(nextUserId);
  };

  const refreshUsers = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/sain/users`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const loadedUsers = Array.isArray(data.users) ? data.users : [];
      setUsers(loadedUsers);
      setApiStatus('connected');
      setApiError(loadedUsers.length ? '' : 'В backend пока нет пользователей. Сначала организаторы должны передать данные через /run.');
      if (!loadedUsers.some((user) => user.user_id === selectedUserId)) {
        setSelectedUserId(loadedUsers[0]?.user_id || '');
      }
      setUserRefreshKey((value) => value + 1);
    } catch (error) {
      console.error('Не удалось обновить список пользователей:', error);
      setApiStatus('offline');
      setApiError('Не удалось обновить список пользователей. Проверь backend.');
    }
  };

  const metrics = userSummary?.metrics || {};
  const eventCounts = metrics.event_counts_90d || {};
  const habitStats = metrics.habit_stats_90d || {};
  const calendarCount = Object.entries(eventCounts)
    .filter(([type]) => ['calendar', 'meeting', 'appointment', 'schedule'].includes(type.toLowerCase()))
    .reduce((sum, [, count]) => sum + Number(count || 0), 0);
  const waterCount = Object.entries(eventCounts)
    .filter(([type]) => ['water', 'water_intake', 'hydration', 'drink'].includes(type.toLowerCase()))
    .reduce((sum, [, count]) => sum + Number(count || 0), 0);
  const topHabit = Object.entries(habitStats).sort((a, b) => Number(b[1]) - Number(a[1]))[0];
  const assistantBriefing = !selectedUserId
    ? 'Пока нет загруженных пользователей. После передачи данных организаторами SAIN сможет показать персональную историю.'
    : isLoadingSummary
      ? 'Загружаю профиль и историю пользователя из памяти SAIN…'
      : metrics.total_events_90d
        ? `За последние 90 дней в памяти ${metrics.total_events_90d} событий. За последние 14 дней — ${metrics.total_events_14d || 0}. Рекомендации будут основаны на этих данных.`
        : 'История пользователя пока пуста. Я не буду придумывать показатели и смогу персонализировать рекомендации, когда появятся события.';

  const persistDashboard = async (widgetIds, configs = widgetConfigs, modeId = activeModeId) => {
    if (!dashboardLoaded || !selectedUserId) return;
    try {
      const response = await fetch(`${API_BASE}/api/sain/dashboard`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: selectedUserId,
          widget_ids: widgetIds,
          widget_configs: configs,
          active_mode_id: modeId
        })
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (Array.isArray(data.modes)) setSavedModes(data.modes);
      setApiError('');
    } catch (error) {
      console.error('Не удалось сохранить экран SAIN:', error);
      setApiError('Изменения экрана не сохранены на сервере. Проверь соединение и повтори действие.');
    }
  };

  const applyDashboard = (nextIds, nextConfigs = widgetConfigs, nextModeId = activeModeId) => {
    const uniqueIds = [...new Set(nextIds)].filter((id) => allWidgetIds.includes(id)).slice(0, 12);
    setMorningWidgetIds(uniqueIds);
    setWidgetConfigs(nextConfigs);
    setActiveModeId(nextModeId);
    persistDashboard(uniqueIds, nextConfigs, nextModeId);
  };

  const handleScenarioChange = (id) => {
    const scenario = SCENARIOS.find((item) => item.id === id);
    if (!scenario) return;
    applyDashboard(scenario.widgetIds, widgetConfigs, id);
  };

  const addWidget = (widgetId) => {
    if (morningWidgetIds.includes(widgetId) || morningWidgetIds.length >= 12) return;
    applyDashboard([...morningWidgetIds, widgetId]);
  };

  const removeWidget = (widgetId) => {
    applyDashboard(morningWidgetIds.filter((id) => id !== widgetId));
  };

  const moveWidget = (widgetId, direction) => {
    const currentIndex = morningWidgetIds.indexOf(widgetId);
    const nextIndex = currentIndex + direction;
    if (currentIndex < 0 || nextIndex < 0 || nextIndex >= morningWidgetIds.length) return;
    const nextIds = [...morningWidgetIds];
    [nextIds[currentIndex], nextIds[nextIndex]] = [nextIds[nextIndex], nextIds[currentIndex]];
    applyDashboard(nextIds);
  };

  const updateWidgetSize = (widgetId) => {
    const currentSize = widgetConfigs[widgetId]?.size || allWidgets.find((item) => item.id === widgetId)?.size || 'half';
    const nextConfigs = {
      ...widgetConfigs,
      [widgetId]: { ...widgetConfigs[widgetId], size: currentSize === 'full' ? 'half' : 'full' }
    };
    applyDashboard(morningWidgetIds, nextConfigs);
  };

  const activateSavedMode = (mode) => {
    setActiveModeId(mode.id);
    setWidgetConfigs(mode.widget_configs || {});
    setMorningWidgetIds(mode.widget_ids || []);
    persistDashboard(mode.widget_ids || [], mode.widget_configs || {}, mode.id);
  };

  const sendSainMessage = async (message) => {
    const cleanMessage = message.trim();
    if (!cleanMessage || isSending) return;
    if (!selectedUserId) {
      setMessages((prev) => [...prev, { sender: 'agent', text: 'Сначала дождись загрузки данных пользователя из backend.' }]);
      return;
    }
    const pendingId = `pending-${Date.now()}`;
    setIsSending(true);
    setMessages((prev) => [
      ...prev,
      { sender: 'user', text: cleanMessage },
      { id: pendingId, sender: 'agent', text: 'SAIN обрабатывает запрос…', pending: true }
    ]);
    try {
      const response = await fetch(`${API_BASE}/api/sain/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: selectedUserId,
          message: cleanMessage,
          history: messages
            .filter((item) => !item.pending && typeof item.text === 'string')
            .slice(-12)
            .map((item) => ({
              role: item.sender === 'user' ? 'user' : 'assistant',
              content: item.text
            }))
        })
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${response.status}`);
      }
      const data = await response.json();
      setMessages((prev) => prev.map((item) =>
        item.id === pendingId ? { sender: 'agent', text: data.reply || 'Готово.' } : item
      ));
      if (data.dashboard) {
        const dashboard = data.dashboard;
        if (Array.isArray(dashboard.widget_ids)) setMorningWidgetIds(dashboard.widget_ids);
        if (dashboard.widget_configs) setWidgetConfigs(dashboard.widget_configs);
        if (dashboard.active_mode_id) {
          setActiveModeId(dashboard.active_mode_id);
        }
        if (Array.isArray(dashboard.modes)) setSavedModes(dashboard.modes);
      }
    } catch (error) {
      console.error('Ошибка чата SAIN:', error);
      setMessages((prev) => prev.map((item) =>
        item.id === pendingId
          ? { sender: 'agent', text: `Не удалось выполнить запрос: ${error.message || 'ошибка backend'}. Проверь соединение и настройки модели.` }
          : item
      ));
    } finally {
      setIsSending(false);
    }
  };

  // Отправка из строки ввода на главном экране.
  const handleQuickSubmit = (e) => {
    e.preventDefault();
    const query = quickInput.trim();
    setView('chat');
    setQuickInput('');
    if (query) sendSainMessage(query);
  };

  // Отправка сообщения из чата.
  const handleChatSend = (e) => {
    e.preventDefault();
    const message = chatInput.trim();
    if (!message || isSending) return;
    setChatInput('');
    sendSainMessage(message);
  };

  const handleAskPreset = (preset) => {
    setView('chat');
    sendSainMessage(preset.q);
  };

  // Каталог 12 виджетов со стабильным размером текста и Liquid Glass иконками (стиль Apple / iOS)
  const allWidgets = useMemo(() => [
    {
      id: 'sleep_card',
      category: 'recovery',
      size: 'full',
      icon: <Moon size={17} strokeWidth={2.2} className="liquid-icon icon-sleep" />,
      tag: 'Сон',
      render: () => {
        const sleep = metrics.latest_sleep;
        return (
          <div className="card-body">
            {sleep ? (
              <>
                <div className="val-large">{formatHours(Number(sleep.duration))}</div>
                <div className="sub-text">Последняя запись: {formatDate(sleep.date)}</div>
              </>
            ) : (
              <div className="sub-text">Нет записей о сне за последние 14 дней.</div>
            )}
          </div>
        );
      }
    },
    {
      id: 'calendar_brief',
      category: 'focus',
      size: 'half',
      icon: <Calendar size={17} strokeWidth={2.2} className="liquid-icon icon-calendar" />,
      tag: 'Календарь',
      render: () => (
        <div className="card-body">
          <div className="val-large">{calendarCount}</div>
          <div className="val-title">Записей календаря</div>
          <div className="sub-text">За последние 90 дней в полученных данных.</div>
        </div>
      )
    },
    {
      id: 'restart_card',
      category: 'habits',
      size: 'full',
      icon: <Sprout size={17} strokeWidth={2.2} className="liquid-icon icon-sprout" />,
      tag: 'Поддержка',
      render: () => (
        <div className="card-body">
          <div className="val-large">{metrics.failed_habits_14d || 0}</div>
          <div className="val-title">Отметок о пропуске привычки</div>
          <div className="sub-text">По событиям за последние 14 дней. Это не оценка пользователя.</div>
        </div>
      )
    },
    {
      id: 'workout_suggest',
      category: 'activity',
      size: 'full',
      icon: <Zap size={17} strokeWidth={2.2} className="liquid-icon icon-zap" />,
      tag: 'Активность',
      render: () => (
        <div className="card-body">
          <div className="val-large">{metrics.workout_count_14d || 0}</div>
          <div className="val-title">Записей о тренировках</div>
          <div className="sub-text">За последние 14 дней. SAIN не предполагает нагрузку без данных.</div>
        </div>
      )
    },
    {
      id: 'steps_ring',
      category: 'activity',
      size: 'half',
      icon: <Footprints size={17} strokeWidth={2.2} className="liquid-icon icon-steps" />,
      tag: 'Шаги',
      render: () => {
        const steps = metrics.latest_steps;
        const percent = steps?.target > 0 ? Math.min(100, Math.round((steps.current / steps.target) * 100)) : null;
        return (
          <div className="card-body">
            {steps ? (
              <div className="steps-progress-box">
                <div className="steps-numbers">
                  <span className="val-large">{Number(steps.current).toLocaleString('ru-RU')}</span>
                  {percent !== null && <span className="pill pill-good">{percent}%</span>}
                </div>
                {percent !== null && <div className="progress-bar"><div className="progress-fill primary" style={{ width: `${percent}%` }} /></div>}
                <div className="sub-text">{steps.target ? `из ${Number(steps.target).toLocaleString('ru-RU')} шагов` : `Последняя запись: ${formatDate(steps.date)}`}</div>
              </div>
            ) : <div className="sub-text">Данные о количестве шагов не поступали.</div>}
          </div>
        );
      }
    },
    {
      id: 'water_tracker',
      category: 'habits',
      size: 'half',
      icon: <Droplets size={17} strokeWidth={2.2} className="liquid-icon icon-water" />,
      tag: 'Вода',
      render: () => (
        <div className="card-body">
          <div className="val-large">{waterCount}</div>
          <div className="val-title">Записей о воде</div>
          <div className="sub-text">За последние 90 дней. Объём не показывается, если он не указан в источнике.</div>
        </div>
      )
    },
    {
      id: 'day_plan',
      category: 'focus',
      size: 'full',
      icon: <ClipboardList size={17} strokeWidth={2.2} className="liquid-icon icon-plan" />,
      tag: 'План дня',
      render: () => (
        <div className="card-body">
          <div className="val-title">{userSummary?.profile?.goal || 'Цель пока не указана'}</div>
          <div className="sub-text">Событий в истории за 14 дней: {metrics.total_events_14d || 0}. План задач можно сформировать в диалоге с SAIN.</div>
        </div>
      )
    },
    {
      id: 'habit_streak',
      category: 'habits',
      size: 'half',
      icon: <Flame size={17} strokeWidth={2.2} className="liquid-icon icon-streak" />,
      tag: 'Серия',
      render: () => (
        <div className="card-body">
          {topHabit ? (
            <>
              <div className="val-large">{topHabit[1]}</div>
              <div className="val-title">Записей: {topHabit[0]}</div>
              <div className="sub-text">Частота событий за 90 дней. Непрерывная серия не вычисляется без календарной истории.</div>
            </>
          ) : <div className="sub-text">Пока недостаточно событий для анализа привычек.</div>}
        </div>
      )
    },
    {
      id: 'recovery_tip',
      category: 'recovery',
      size: 'half',
      icon: <Leaf size={17} strokeWidth={2.2} className="liquid-icon icon-leaf" />,
      tag: 'Дыхание',
      render: () => (
        <div className="card-body">
          <div className="val-title">Короткая пауза</div>
          <div className="sub-text">Можно ненадолго отвлечься от экрана и вернуться к делам в удобном темпе.</div>
        </div>
      )
    },
    {
      id: 'energy_forecast',
      category: 'focus',
      size: 'full',
      icon: <BatteryCharging size={17} strokeWidth={2.2} className="liquid-icon icon-energy" />,
      tag: 'Циркадный ритм',
      render: () => (
        <div className="card-body">
          <div className="val-title">Прогноз пока недоступен</div>
          <div className="sub-text">В поступившей истории недостаточно данных, чтобы достоверно оценить личное окно энергии.</div>
        </div>
      )
    },
    {
      id: 'evening_reflect',
      category: 'recovery',
      size: 'half',
      icon: <Sparkles size={17} strokeWidth={2.2} className="liquid-icon icon-evening" />,
      tag: 'Вечер',
      render: () => (
        <div className="card-body">
          <div className="val-large">{metrics.total_events_90d || 0}</div>
          <div className="val-title">Событий в памяти</div>
          <div className="sub-text">Последние 90 дней. Ритуалы не назначаются автоматически.</div>
        </div>
      )
    },
    {
      id: 'goal_progress',
      category: 'habits',
      size: 'half',
      icon: <Target size={17} strokeWidth={2.2} className="liquid-icon icon-target" />,
      tag: 'Цель месяца',
      render: () => (
        <div className="card-body">
          <div className="val-title">{userSummary?.profile?.goal || 'Цель не указана в профиле'}</div>
          <div className="sub-text">SAIN отслеживает только те показатели, которые действительно присутствуют в данных.</div>
        </div>
      )
    }
  ], [userSummary, metrics, eventCounts, habitStats, calendarCount, waterCount, topHabit]);

  const morningWidgets = useMemo(() => {
    if (!selectedUserId) return [];
    return morningWidgetIds
      .map((id) => allWidgets.find((widget) => widget.id === id))
      .filter(Boolean)
      .map((widget) => ({
        ...widget,
        size: widgetConfigs[widget.id]?.size || widget.size,
        tag: widgetConfigs[widget.id]?.title || widget.tag
      }));
  }, [selectedUserId, morningWidgetIds, allWidgets, widgetConfigs]);

  const filteredCatalog = useMemo(() => {
    const widgets = allWidgets.map((widget) => ({
      ...widget,
      size: widgetConfigs[widget.id]?.size || widget.size,
      tag: widgetConfigs[widget.id]?.title || widget.tag
    }));
    if (activeCategory === 'all') return widgets;
    return widgets.filter((w) => w.category === activeCategory);
  }, [activeCategory, allWidgets, widgetConfigs]);

  const selectedWidget = allWidgets.find((widget) => widget.id === selectedWidgetId);

  useEffect(() => {
    if (!selectedWidgetId) return undefined;
    const handleEscape = (event) => {
      if (event.key === 'Escape') setSelectedWidgetId(null);
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [selectedWidgetId]);

  return (
    <div className="viewport">
      <div className="app-shell">
        {/* ВЕРХНИЙ СТАТУС */}
        <header className="app-header">
          <div className="header-left">
            <span className="app-logo">SAIN</span>
          </div>
          <div className="header-right">
            {users.length > 0 ? (
              <select
                className="header-user-select"
                value={selectedUserId}
                onChange={handleUserChange}
                aria-label="Выбрать пользователя"
                title="Пользователь, чью историю использует SAIN"
              >
                {users.map((user) => (
                  <option key={user.user_id} value={user.user_id}>
                    {user.label} · {user.external_id}
                  </option>
                ))}
              </select>
            ) : (
              <span className={`backend-status ${apiStatus === 'connected' ? 'is-online' : ''}`}>
                {apiStatus === 'connected' ? 'Нет пользователей' : apiStatus === 'connecting' ? 'Подключение…' : 'Backend недоступен'}
              </span>
            )}
            <button className="header-refresh-button" type="button" onClick={refreshUsers} aria-label="Обновить пользователей" title="Обновить список пользователей и историю">
              <RotateCcw size={13} />
            </button>
            <span className="time-badge-header">{currentTime}</span>
          </div>
        </header>

        {/* ------------------------------------------------------------- */}
        {/* 1. ЭКРАН УТРА (ГЛАВНЫЙ ЭКРАН)                                 */}
        {/* ------------------------------------------------------------- */}
        {view === 'morning' && (
          <main className="content-area">
            {/* КАРТОЧКА АССИСТЕНТА: ТЕКСТ СВЕРХУ, СТРОКА ВВОДА ВНИЗУ */}
            <div className="assistant-card">
              <div className="assistant-card-top">
                <div className="assistant-brand">
                  <span className="dot-online" />
                  <span className="assistant-name">SAIN-помощник</span>
                </div>
              </div>

              {/* ТЕКСТ БРИФИНГА СВЕРХУ */}
              <p className="assistant-text">{assistantBriefing}</p>
              {selectedUserId && userSummary?.profile?.goal ? (
                <p className="assistant-user-goal">Цель: {String(userSummary.profile.goal)}</p>
              ) : null}
              {apiError && <div className="backend-error-banner" role="status">{apiError}</div>}

              {/* СТРОКА ВВОДА ВНИЗУ КАРТОЧКИ */}
              <form className="assistant-search-bar" onSubmit={handleQuickSubmit}>
                <Search size={15} color="#ffffff" />
                <input
                  type="text"
                  placeholder={selectedUserId ? 'Спроси SAIN о своей истории...' : 'Ожидание данных пользователей...'}
                  value={quickInput}
                  disabled={!selectedUserId || isSending}
                  onChange={(e) => setQuickInput(e.target.value)}
                />
                <button type="submit" className="btn-search-arrow" aria-label="Спросить" disabled={!selectedUserId || isSending}>
                  <ArrowRight size={14} color="#ffffff" />
                </button>
              </form>
            </div>

            {/* СЕКЦИЯ КАРТОЧЕК С КНОПКОЙ КАТАЛОГА РЯДОМ */}
            <div className="section-header-row">
              <div>
                <h3 className="section-title">Карточки на сегодня</h3>
                <span className="sub-text">Собрано под контекст дня</span>
              </div>
              <div className="dashboard-header-actions">
                <button className="btn-edit-dashboard" disabled={!selectedUserId} onClick={() => setIsEditingDashboard((value) => !value)}>
                  {isEditingDashboard ? 'Готово' : 'Настроить'}
                </button>
                <button className="btn-catalog-pill" onClick={() => setView('catalog')}>
                  <span>Каталог</span>
                  <ArrowRight size={13} color="#f9f9f9" />
                </button>
              </div>
            </div>

            {/* СЕТКА ВИДЖЕТОВ: ДВА МАЛЕНЬКИХ ВИДЖЕТА ВСЕГДА В ОДНУ СТРОКУ */}
            <div className="grid-cards-dense">
              {morningWidgets.map((w) => (
                <div
                  key={w.id}
                  className={`ui-card widget-open-card ${w.size === 'full' ? 'span-2' : ''}`}
                  role="button"
                  tabIndex={0}
                  onClick={(event) => {
                    if (event.target.closest('button, input, .task-row')) return;
                    setSelectedWidgetId(w.id);
                  }}
                  onKeyDown={(event) => {
                    if ((event.key === 'Enter' || event.key === ' ') && !event.target.closest('button, input, .task-row')) {
                      setSelectedWidgetId(w.id);
                    }
                  }}
                >
                  <div className="card-top-bar">
                    <span className="icon-wrap">{w.icon}</span>
                    <span className="card-tag">{w.tag}</span>
                    {isEditingDashboard && (
                      <div className="widget-edit-actions">
                        <button type="button" aria-label="Переместить выше" onClick={() => moveWidget(w.id, -1)}><ChevronUp size={14} /></button>
                        <button type="button" aria-label="Переместить ниже" onClick={() => moveWidget(w.id, 1)}><ChevronDown size={14} /></button>
                        <button type="button" aria-label="Убрать виджет" onClick={() => removeWidget(w.id)}><X size={14} /></button>
                      </div>
                    )}
                    {!isEditingDashboard && <Maximize2 className="widget-expand-icon" size={13} />}
                  </div>
                  {w.render()}
                </div>
              ))}
              {morningWidgets.length === 0 && (
                <div className="dashboard-empty-state">
                  На экране пока нет виджетов. Открой каталог или попроси SAIN добавить нужные карточки.
                </div>
              )}
            </div>
          </main>
        )}

        {/* ------------------------------------------------------------- */}
        {/* 2. ДИАЛОГ С АССИСТЕНТОМ                                       */}
        {/* ------------------------------------------------------------- */}
        {view === 'chat' && (
          <main className="chat-area view-transition">
            {/* ШАПКА ДИАЛОГА */}
            <div className="chat-top-nav">
              <button className="btn-back-clean" onClick={() => setView('morning')}>
                <ArrowLeft size={16} color="#f9f9f9" />
                <span>Назад к утру</span>
              </button>
              <div className="assistant-title-badge">
                <span className="dot-online" />
                <span>SAIN-помощник</span>
              </div>
            </div>

            {/* ПОТОК СООБЩЕНИЙ */}
            <div className="chat-flow">
              {messages.map((m, i) => (
                <div
                  key={m.id || i}
                  className={`msg-bubble ${m.sender === 'user' ? 'msg-user' : 'msg-agent'} ${m.pending ? 'msg-pending' : ''}`}
                >
                  {m.text}
                </div>
              ))}
            </div>

            {/* РЕЖИМЫ И ВОПРОСЫ ВНИЗУ НАД ВВОДОМ */}
            <div className="chat-bottom-suggestions">
              {/* РЕЖИМЫ КОНТЕКСТА */}
              <div className="agent-context-strip">
                <span className="context-label">Режим:</span>
                {SCENARIOS.map((sc) => (
                  <button
                    key={sc.id}
                    type="button"
                    className={`context-pill ${activeModeId === sc.id ? 'active' : ''}`}
                    onClick={() => {
                      handleScenarioChange(sc.id);
                      setMessages((prev) => [...prev, { sender: 'agent', text: `Режим «${sc.title}» включён.` }]);
                    }}
                  >
                    {sc.title}
                  </button>
                ))}
                {savedModes.filter((mode) => !SCENARIOS.some((scenario) => scenario.id === mode.id)).map((mode) => (
                  <button
                    key={mode.id}
                    type="button"
                    className={`context-pill ${activeModeId === mode.id ? 'active' : ''}`}
                    onClick={() => {
                      activateSavedMode(mode);
                      setMessages((prev) => [...prev, { sender: 'agent', text: `Режим «${mode.name}» включён.` }]);
                    }}
                  >
                    {mode.name}
                  </button>
                ))}
              </div>

              {/* УВЕЛИЧЕННЫЕ БЫСТРЫЕ ВОПРОСЫ */}
              <div className="chips-container-bottom">
                {SMART_PRESETS.map((p, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="preset-chip-large"
                    onClick={() => handleAskPreset(p)}
                  >
                    {p.q}
                  </button>
                ))}
              </div>
            </div>

            {/* СТРОКА ВВОДА С ЖИДКИМ СТЕКЛОМ */}
            <form className="chat-form-row" onSubmit={handleChatSend}>
              <input
                type="text"
                placeholder={selectedUserId ? 'Спроси SAIN о своей истории...' : 'Сначала загрузите данные пользователя'}
                value={chatInput}
                disabled={!selectedUserId || isSending}
                onChange={(e) => setChatInput(e.target.value)}
                autoFocus
              />
              <button type="submit" className="btn-send-glass" aria-label="Отправить" disabled={isSending}>
                <Send size={15} color={ICON_COLOR} />
              </button>
            </form>
          </main>
        )}

        {/* ------------------------------------------------------------- */}
        {/* 3. КАТАЛОГ ВСЕХ 12 ВИДЖЕТОВ                                   */}
        {/* ------------------------------------------------------------- */}
        {view === 'catalog' && (
          <main className="content-area view-transition">
            <div className="catalog-header-bar">
              <button className="btn-back-clean" onClick={() => setView('morning')}>
                <ArrowLeft size={16} color="#f9f9f9" />
                <span>Назад к утру</span>
              </button>
            </div>

            <div className="category-tabs">
              {[
                { id: 'all', label: 'Все (12)' },
                { id: 'recovery', label: 'Восстановление' },
                { id: 'activity', label: 'Активность' },
                { id: 'focus', label: 'Фокус' },
                { id: 'habits', label: 'Привычки' }
              ].map((c) => (
                <button
                  key={c.id}
                  className={`cat-pill ${activeCategory === c.id ? 'active' : ''}`}
                  onClick={() => setActiveCategory(c.id)}
                >
                  {c.label}
                </button>
              ))}
            </div>

            <div className="grid-cards-dense">
              {filteredCatalog.map((w) => {
                const isOnDashboard = morningWidgetIds.includes(w.id);
                return (
                  <div
                    key={w.id}
                    className={`ui-card widget-open-card ${w.size === 'full' ? 'span-2' : ''}`}
                    role="button"
                    tabIndex={0}
                    onClick={(event) => {
                      if (event.target.closest('button, input, .task-row')) return;
                      setSelectedWidgetId(w.id);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') setSelectedWidgetId(w.id);
                    }}
                  >
                    <div className="card-top-bar">
                      <span className="icon-wrap">{w.icon}</span>
                      <span className="card-tag">{w.tag}</span>
                      <Maximize2 className="widget-expand-icon" size={13} />
                    </div>
                    {w.render()}
                    <button
                      type="button"
                      className={`catalog-widget-action ${isOnDashboard ? 'is-added' : ''}`}
                      disabled={!selectedUserId}
                      onClick={() => isOnDashboard ? removeWidget(w.id) : addWidget(w.id)}
                    >
                      {isOnDashboard ? 'Убрать с экрана' : 'Добавить на экран'}
                    </button>
                  </div>
                );
              })}
            </div>
          </main>
        )}

        {selectedWidget && (
          <div className="widget-modal-backdrop" onClick={() => setSelectedWidgetId(null)}>
            <section
              className="widget-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="widget-modal-title"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="widget-modal-header">
                <div>
                  <div className="widget-modal-eyebrow">ВИДЖЕТ SAIN</div>
                  <h2 id="widget-modal-title">{widgetConfigs[selectedWidget.id]?.title || selectedWidget.tag}</h2>
                </div>
                <button className="widget-modal-close" type="button" onClick={() => setSelectedWidgetId(null)} aria-label="Закрыть">
                  <X size={18} />
                </button>
              </div>
              <div className="widget-modal-content">{selectedWidget.render()}</div>
              <div className="widget-modal-actions">
                <button
                  type="button"
                  className="widget-modal-secondary"
                  disabled={!selectedUserId}
                  onClick={() => updateWidgetSize(selectedWidget.id)}
                >
                  {widgetConfigs[selectedWidget.id]?.size === 'full' || (!widgetConfigs[selectedWidget.id]?.size && selectedWidget.size === 'full')
                    ? 'Сделать компактным'
                    : 'Растянуть на всю ширину'}
                </button>
                {morningWidgetIds.includes(selectedWidget.id) ? (
                  <button type="button" className="widget-modal-primary" disabled={!selectedUserId} onClick={() => removeWidget(selectedWidget.id)}>
                    Убрать с экрана
                  </button>
                ) : (
                  <button type="button" className="widget-modal-primary" disabled={!selectedUserId} onClick={() => addWidget(selectedWidget.id)}>
                    Добавить на экран
                  </button>
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
