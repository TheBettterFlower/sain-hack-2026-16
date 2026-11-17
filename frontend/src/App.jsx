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
  Check,
  RotateCcw,
  Plus,
  Minus,
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
const API_BASE = runtimeConfig.SAIN_API_URL || 'http://localhost:8000';
const SAIN_USER_ID = runtimeConfig.SAIN_USER_ID || 'demo-user';

// -------------------------------------------------------------
// РЕЖИМЫ КОНТЕКСТА (Паттерны 90 дней — живут в окне Ассистента)
// -------------------------------------------------------------
const SCENARIOS = [
  {
    id: 'flight',
    title: 'Перед перелётом',
    badge: 'Паттерн: вечерний перелёт',
    agentGreeting:
      'Доброе утро! Давай начнем этот день вместе',
    // Маленькие виджеты (календарь и вода) идут парой, чтобы занять одну общую строку
    widgetIds: ['calendar_brief', 'water_tracker', 'sleep_card', 'day_plan']
  },
  {
    id: 'restart',
    title: 'После срыва привычки',
    badge: 'Паттерн: пятничный спад',
    agentGreeting:
      'Конец недели сбил ритм. Никаких упрёков: восстанавливаем темп мягко и без стресса.',
    // Маленькие виджеты (восстановление и стрик) идут парой в одну строку
    widgetIds: ['recovery_tip', 'habit_streak', 'restart_card', 'workout_suggest']
  },
  {
    id: 'peak',
    title: 'Пик продуктивности',
    badge: 'Паттерн: высокий ресурс',
    agentGreeting:
      'Ресурс 92%. Окно пикового фокуса: 10:00–13:00. Лучшее время для ключевых задач.',
    // Маленькие виджеты (шаги и цель) идут парой в одну строку
    widgetIds: ['steps_ring', 'goal_progress', 'energy_forecast', 'day_plan']
  }
];

// -------------------------------------------------------------
// БЫСТРЫЕ ВОПРОСЫ К АССИСТЕНТУ (ЛАКОНИЧНЫЕ ОТВЕТЫ ИЗ ПАМЯТИ 90 ДНЕЙ)
// -------------------------------------------------------------
const SMART_PRESETS = [
  {
    q: '✈️ Сон перед перелётом',
    a: 'Перед рейсами глубокий сон падает на 35%. Собери вещи до 18:00 и выпей 500 мл воды до посадки.'
  },
  {
    q: '📉 Спад привычек к пятнице',
    a: 'К четвергу накапливается дефицит сна (~45 мин/день). Сдвиг отбоя на 30 мин раньше в среду сохранит баланс.'
  },
  {
    q: '⚡ Окно пиковой энергии',
    a: 'Максимум фокуса — с 10:00 до 13:00. После 14:30 наступит спад: запланируй рутину или прогулку.'
  },
  {
    q: '💧 Норма воды до обеда',
    a: 'Твоя норма до 14:00 — 4 стакана (1 литр), чтобы компенсировать сухой воздух в самолёте.'
  }
];

export default function App() {
  const [view, setView] = useState('morning'); // 'morning' | 'chat' | 'catalog'
  const [activeScenarioId, setActiveScenarioId] = useState('flight');
  const [activeModeId, setActiveModeId] = useState('flight');
  const [activeCategory, setActiveCategory] = useState('all');
  const [morningWidgetIds, setMorningWidgetIds] = useState(SCENARIOS[0].widgetIds);
  const [widgetConfigs, setWidgetConfigs] = useState({});
  const [savedModes, setSavedModes] = useState([]);
  const [dashboardLoaded, setDashboardLoaded] = useState(false);
  const [isEditingDashboard, setIsEditingDashboard] = useState(false);
  const [selectedWidgetId, setSelectedWidgetId] = useState(null);
  const [isSending, setIsSending] = useState(false);
  const [customGreeting, setCustomGreeting] = useState('');
  const allWidgetIds = [
    'sleep_card', 'calendar_brief', 'restart_card', 'workout_suggest',
    'steps_ring', 'water_tracker', 'day_plan', 'habit_streak',
    'recovery_tip', 'energy_forecast', 'evening_reflect', 'goal_progress'
  ];

  // Интерактивные данные
  const [quickInput, setQuickInput] = useState('');
  const [waterCups, setWaterCups] = useState(2);
  const [planTasks, setPlanTasks] = useState([
    { id: 1, text: 'Прогулка 20 мин на утреннем солнце', done: true },
    { id: 2, text: 'Глубокий фокус-блок 10:00 – 12:30', done: false },
    { id: 3, text: 'Собрать ручную кладь до 18:00', done: false }
  ]);
  const [isBreathing, setIsBreathing] = useState(false);
  const [breathPhase, setBreathPhase] = useState('Вдох 4 сек');

  // Чат с ассистентом
  const [messages, setMessages] = useState([
    {
      sender: 'agent',
      text: 'Я SAIN. Могу ответить на вопросы и настроить твой утренний экран. Чем займёмся?'
    }
  ]);
  const [chatInput, setChatInput] = useState('');

  const currentScenario = useMemo(
    () => SCENARIOS.find((s) => s.id === activeScenarioId) || SCENARIOS[0],
    [activeScenarioId]
  );

  // Загружаем экран и пользовательские режимы из SQLite.
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/sain/state/${encodeURIComponent(SAIN_USER_ID)}`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data) => {
        if (cancelled) return;
        if (Array.isArray(data.widget_ids)) setMorningWidgetIds(data.widget_ids);
        if (data.widget_configs && typeof data.widget_configs === 'object') {
          setWidgetConfigs(data.widget_configs);
        }
        if (Array.isArray(data.modes)) setSavedModes(data.modes);
        if (data.active_mode_id) {
          setActiveModeId(data.active_mode_id);
          const scenario = SCENARIOS.find((item) => item.id === data.active_mode_id);
          if (scenario) setActiveScenarioId(scenario.id);
          else setCustomGreeting('Пользовательский режим активирован. Настроим утро под твои задачи.');
        }
      })
      .catch((error) => {
        console.warn('Не удалось загрузить настройки SAIN; используется локальный экран.', error);
      })
      .finally(() => {
        if (!cancelled) setDashboardLoaded(true);
      });
    return () => { cancelled = true; };
  }, []);

  const persistDashboard = async (widgetIds, configs = widgetConfigs, modeId = activeModeId) => {
    if (!dashboardLoaded) return;
    try {
      const response = await fetch(`${API_BASE}/api/sain/dashboard`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: SAIN_USER_ID,
          widget_ids: widgetIds,
          widget_configs: configs,
          active_mode_id: modeId
        })
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (Array.isArray(data.modes)) setSavedModes(data.modes);
    } catch (error) {
      console.error('Не удалось сохранить экран SAIN:', error);
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
    setActiveScenarioId(id);
    setCustomGreeting('');
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
    const scenario = SCENARIOS.find((item) => item.id === mode.id);
    if (scenario) {
      setActiveScenarioId(scenario.id);
      setCustomGreeting('');
    } else {
      setActiveScenarioId('custom');
      setCustomGreeting(`Режим «${mode.name}» включён. Экран настроен под выбранный сценарий.`);
    }
    persistDashboard(mode.widget_ids || [], mode.widget_configs || {}, mode.id);
  };

  const sendSainMessage = async (message) => {
    const cleanMessage = message.trim();
    if (!cleanMessage || isSending) return;
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
          user_id: SAIN_USER_ID,
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
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
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
          const scenario = SCENARIOS.find((item) => item.id === dashboard.active_mode_id);
          if (scenario) {
            setActiveScenarioId(scenario.id);
            setCustomGreeting('');
          } else {
            const mode = (dashboard.modes || []).find((item) => item.id === dashboard.active_mode_id);
            setActiveScenarioId('custom');
            if (mode) setCustomGreeting(`Режим «${mode.name}» включён.`);
          }
        }
        if (Array.isArray(dashboard.modes)) setSavedModes(dashboard.modes);
      }
    } catch (error) {
      console.error('Ошибка чата SAIN:', error);
      setMessages((prev) => prev.map((item) =>
        item.id === pendingId
          ? { sender: 'agent', text: 'Не удалось подключиться к SAIN API. Проверь, что backend запущен и доступен по адресу API.' }
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

  const toggleTask = (id) => {
    setPlanTasks((prev) =>
      prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t))
    );
  };

  // Каталог 12 виджетов со стабильным размером текста и Liquid Glass иконками (стиль Apple / iOS)
  const allWidgets = useMemo(() => [
    {
      id: 'sleep_card',
      category: 'recovery',
      size: 'full',
      icon: <Moon size={17} strokeWidth={2.2} className="liquid-icon icon-sleep" />,
      tag: 'Сон',
      render: () => (
        <div className="card-body">
          <div className="row-between">
            <div>
              <div className="val-large">7ч 45м</div>
              <div className="sub-text">в кровати 8ч 15м</div>
            </div>
            {/* Плашка сна отлично: приятно салатовая */}
            <span className="pill pill-good">88 • Отлично</span>
          </div>
          <div className="hypnogram">
            <div className="h-bar deep" style={{ width: '25%' }} />
            <div className="h-bar rem" style={{ width: '22%' }} />
            <div className="h-bar light" style={{ width: '53%' }} />
          </div>
          <div className="row-between sub-text" style={{ fontSize: '11px' }}>
            <span>Глубокий: 1ч 55м (25%)</span>
            <span>REM: 1ч 40м</span>
            <span>Лёгкий: 4ч 10м</span>
          </div>
        </div>
      )
    },
    {
      id: 'calendar_brief',
      category: 'focus',
      size: 'half',
      icon: <Calendar size={17} strokeWidth={2.2} className="liquid-icon icon-calendar" />,
      tag: 'Календарь',
      render: () => (
        <div className="card-body">
          <div className="row-between">
            <div className="val-accent">В 11:00</div>
            <span className="pill pill-azure">Через 2ч</span>
          </div>
          <div className="val-title">Синхрон команды</div>
          <div className="sub-text">Окно тишины до 10:45</div>
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
          <div className="row-between">
            <div className="val-title">Новый день — чистый старт</div>
            <span className="pill pill-azure">Мягкий темп</span>
          </div>
          <div className="sub-text">
            Срыв привычки — естественная часть процесса. Начнём сегодня этот день в лёгком темпе.
          </div>
          <button className="btn-liquid-glass">
            <RotateCcw size={14} color="#fbfcfd" />
            <span>Продолжить в спокойном ритме</span>
          </button>
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
          <div className="row-between">
            <div>
              <div className="val-large">20 мин</div>
              <div className="sub-text">Мягкая мобильность и стретчинг</div>
            </div>
            <span className="pill pill-azure">Восстановление</span>
          </div>
          <div className="sub-text" style={{ marginTop: '4px' }}>
            Перед вечерним рейсом тяжёлые нагрузки не рекомендуются.
          </div>
        </div>
      )
    },
    {
      id: 'steps_ring',
      category: 'activity',
      size: 'half',
      icon: <Footprints size={17} strokeWidth={2.2} className="liquid-icon icon-steps" />,
      tag: 'Шаги',
      render: () => (
        <div className="card-body">
          <div className="steps-progress-box">
            <div className="steps-numbers">
              <span className="val-large">8 400</span>
              <span className="pill pill-good">84%</span>
            </div>
            <div className="progress-bar">
              <div className="progress-fill primary" style={{ width: '84%' }} />
            </div>
            <div className="sub-text">из 10 000 шагов</div>
          </div>
        </div>
      )
    },
    {
      id: 'water_tracker',
      category: 'habits',
      size: 'half',
      icon: <Droplets size={17} strokeWidth={2.2} className="liquid-icon icon-water" />,
      tag: 'Вода',
      render: () => {
        const isTargetReached = waterCups >= 8;
        return (
          <div className="card-body">
            <div className="row-between">
              <span className="val-large">{waterCups * 250} мл</span>
              {/* Чистый градиентный текст без плашки/объекта сзади */}
              <span className={`pill ${isTargetReached ? 'pill-good' : 'pill-azure'}`}>
                {waterCups}/8 ст.
              </span>
            </div>
            <div className="water-controls">
              <button
                className="btn-counter"
                onClick={() => setWaterCups((c) => Math.max(0, c - 1))}
                disabled={waterCups === 0}
              >
                <Minus size={14} color="#fbfcfd" />
              </button>
              <div className="water-level-track">
                <div
                  className={`water-level-fill ${isTargetReached ? 'complete' : ''}`}
                  style={{ width: `${(waterCups / 8) * 100}%` }}
                />
              </div>
              <button
                className="btn-counter"
                onClick={() => setWaterCups((c) => Math.min(8, c + 1))}
                disabled={waterCups === 8}
              >
                <Plus size={14} color="#fbfcfd" />
              </button>
            </div>
          </div>
        );
      }
    },
    {
      id: 'day_plan',
      category: 'focus',
      size: 'full',
      icon: <ClipboardList size={17} strokeWidth={2.2} className="liquid-icon icon-plan" />,
      tag: 'План дня',
      render: () => {
        const completedCount = planTasks.filter((t) => t.done).length;
        const allDone = completedCount === planTasks.length;
        return (
          <div className="card-body">
            <div className="row-between" style={{ marginBottom: '4px' }}>
              <span className="val-title">Фокус дня</span>
              {/* Компактный индикатор 1/3 или 3/3, без громоздкого текста */}
              <span className={`pill ${allDone ? 'pill-good' : 'pill-azure'}`}>
                {completedCount}/{planTasks.length}
              </span>
            </div>
            <div className="task-list">
              {planTasks.map((t) => (
                <div
                  key={t.id}
                  className={`task-row ${t.done ? 'is-done' : ''}`}
                  onClick={() => toggleTask(t.id)}
                >
                  <div className="checkbox-box">
                    {t.done && <Check size={12} strokeWidth={3} color="#111215" />}
                  </div>
                  <span className="task-label">{t.text}</span>
                </div>
              ))}
            </div>
          </div>
        );
      }
    },
    {
      id: 'habit_streak',
      category: 'habits',
      size: 'half',
      icon: <Flame size={17} strokeWidth={2.2} className="liquid-icon icon-streak" />,
      tag: 'Серия',
      render: () => (
        <div className="card-body">
          <div className="row-between">
            <span className="val-large">5 дней</span>
            <span className="pill pill-good">Активна</span>
          </div>
          <div className="week-grid">
            {['П', 'В', 'С', 'Ч', 'П', 'С', 'В'].map((d, i) => (
              <div key={i} className="week-col">
                <span className={`w-dot ${i < 5 ? 'active' : ''}`} />
                <span className="w-label">{d}</span>
              </div>
            ))}
          </div>
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
          <div className="row-between">
            <div className="val-title">{isBreathing ? breathPhase : 'Пауза 4-7-8'}</div>
            <span className="pill pill-azure">2 мин</span>
          </div>
          <div className="sub-text">Для баланса нервной системы</div>
          <button
            className={`btn-liquid-glass sm ${isBreathing ? 'active' : ''}`}
            onClick={() => {
              setIsBreathing(!isBreathing);
              if (!isBreathing) setBreathPhase('Вдох 4 сек');
            }}
          >
            {isBreathing ? 'Остановить' : 'Начать упражнение'}
          </button>
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
          <div className="row-between">
            <div>
              <div className="val-large">10:00 – 13:00</div>
              <div className="sub-text">Окно максимальной концентрации</div>
            </div>
            <span className="pill pill-good">Ресурс 94%</span>
          </div>
          <div className="timeline-bar">
            <div className="t-segment" style={{ flex: 2 }}>08:00</div>
            <div className="t-segment peak" style={{ flex: 3 }}>10:00–13:00 (Пик)</div>
            <div className="t-segment" style={{ flex: 3 }}>14:00 (Спад)</div>
            <div className="t-segment" style={{ flex: 2 }}>22:00</div>
          </div>
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
          <div className="row-between">
            <div className="val-accent">21:30</div>
            <span className="pill pill-azure">Ритуал</span>
          </div>
          <div className="val-title">Отдых от экранов</div>
          <div className="sub-text">За 60 мин до сна</div>
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
          <div className="row-between">
            <span className="val-large">78%</span>
            <span className="pill pill-good">+4 дня</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill primary" style={{ width: '78%' }} />
          </div>
          <div className="sub-text">Режим сна и активности</div>
        </div>
      )
    }
  ], [waterCups, planTasks, isBreathing, breathPhase]);

  const morningWidgets = useMemo(() => {
    return morningWidgetIds
      .map((id) => allWidgets.find((widget) => widget.id === id))
      .filter(Boolean)
      .map((widget) => ({
        ...widget,
        size: widgetConfigs[widget.id]?.size || widget.size,
        tag: widgetConfigs[widget.id]?.title || widget.tag
      }));
  }, [morningWidgetIds, allWidgets, widgetConfigs]);

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
          <span className="time-badge-header">09:00</span>
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
              <p className="assistant-text">{activeScenarioId === 'custom' ? customGreeting : currentScenario.agentGreeting}</p>

              {/* СТРОКА ВВОДА ВНИЗУ КАРТОЧКИ */}
              <form className="assistant-search-bar" onSubmit={handleQuickSubmit}>
                <Search size={15} color="#ffffff" />
                <input
                  type="text"
                  placeholder="Спроси о сне, перелёте или планах..."
                  value={quickInput}
                  onChange={(e) => setQuickInput(e.target.value)}
                />
                <button type="submit" className="btn-search-arrow" aria-label="Спросить">
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
                <button className="btn-edit-dashboard" onClick={() => setIsEditingDashboard((value) => !value)}>
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
                placeholder="Спроси о сне, перелёте или привычках..."
                value={chatInput}
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
                  onClick={() => updateWidgetSize(selectedWidget.id)}
                >
                  {widgetConfigs[selectedWidget.id]?.size === 'full' || (!widgetConfigs[selectedWidget.id]?.size && selectedWidget.size === 'full')
                    ? 'Сделать компактным'
                    : 'Растянуть на всю ширину'}
                </button>
                {morningWidgetIds.includes(selectedWidget.id) ? (
                  <button type="button" className="widget-modal-primary" onClick={() => removeWidget(selectedWidget.id)}>
                    Убрать с экрана
                  </button>
                ) : (
                  <button type="button" className="widget-modal-primary" onClick={() => addWidget(selectedWidget.id)}>
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
