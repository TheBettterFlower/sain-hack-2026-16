import React, { useState, useMemo } from 'react';
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
  ArrowLeft
} from 'lucide-react';
import './App.css';

// Единый монохромный цвет для иконок
const ICON_COLOR = '#f9f9f9';

// -------------------------------------------------------------
// РЕЖИМЫ КОНТЕКСТА (Паттерны 90 дней — живут в окне Ассистента)
// -------------------------------------------------------------
const SCENARIOS = [
  {
    id: 'flight',
    title: 'Перед перелётом',
    badge: 'Паттерн: вечерний перелёт',
    agentGreeting:
      'Рейс в 20:45. Облегчил план дня и перенёс активность на утро. Советую лечь спать на 40 мин раньше.',
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
  const [activeCategory, setActiveCategory] = useState('all');

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
      text: 'В памяти 90 дней твоего сна, активности и привычек. Чем помочь сегодня?'
    }
  ]);
  const [chatInput, setChatInput] = useState('');

  const currentScenario = useMemo(
    () => SCENARIOS.find((s) => s.id === activeScenarioId) || SCENARIOS[0],
    [activeScenarioId]
  );

  const handleScenarioChange = (id) => {
    setActiveScenarioId(id);
  };

  // Отправка из строки ввода в виджете ассистента
  const handleQuickSubmit = (e) => {
    e.preventDefault();
    const query = quickInput.trim();
    if (query) {
      setMessages((prev) => [
        ...prev,
        { sender: 'user', text: query },
        { sender: 'agent', text: 'Сверяю с историей за 90 дней...' }
      ]);
      setQuickInput('');
    }
    setView('chat');
  };

  // Отправка сообщения из чата
  const handleChatSend = (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    const userMsg = chatInput.trim();
    setChatInput('');
    setMessages((prev) => [...prev, { sender: 'user', text: userMsg }]);

    setTimeout(() => {
      let reply = 'Принято. Учёл в твоём контексте на сегодня.';
      const lower = userMsg.toLowerCase();
      if (lower.includes('сон') || lower.includes('спать')) {
        reply = 'Средний сон за 90 дней — 7ч 25м. Начни подготовку ко сну в 22:30.';
      } else if (lower.includes('рейс') || lower.includes('перелет') || lower.includes('самолет')) {
        reply = 'Рейс в 20:45. Пей больше воды и надень маску для сохранения глубокой фазы сна.';
      }
      setMessages((prev) => [...prev, { sender: 'agent', text: reply }]);
    }, 250);
  };

  const handleAskPreset = (preset) => {
    setMessages((prev) => [
      ...prev,
      { sender: 'user', text: preset.q },
      { sender: 'agent', text: preset.a }
    ]);
    setView('chat');
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
            Срыв привычки — естественная часть процесса. Начнём сегодня без чувства вины и в лёгком темпе.
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
                {waterCups}/8 стаканов
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
          <div className="val-title">Отказ от экранов</div>
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
    return currentScenario.widgetIds
      .map((id) => allWidgets.find((w) => w.id === id))
      .filter(Boolean);
  }, [currentScenario, allWidgets]);

  const filteredCatalog = useMemo(() => {
    if (activeCategory === 'all') return allWidgets;
    return allWidgets.filter((w) => w.category === activeCategory);
  }, [activeCategory, allWidgets]);

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
                  <span className="assistant-name">Ассистент</span>
                </div>
              </div>

              {/* ТЕКСТ БРИФИНГА СВЕРХУ */}
              <p className="assistant-text">{currentScenario.agentGreeting}</p>

              {/* СТРОКА ВВОДА ВНИЗУ КАРТОЧКИ */}
              <form className="assistant-search-bar" onSubmit={handleQuickSubmit}>
                <Search size={15} color="#ffffff" />
                <input
                  type="text"
                  placeholder="Спроси о сне, перелёте или планах..."
                  value={quickInput}
                  onChange={(e) => setQuickInput(e.target.value)}
                  onFocus={() => {
                    if (!quickInput) {
                      setView('chat');
                    }
                  }}
                />
                <button type="submit" className="btn-search-arrow" aria-label="Спросить">
                  <ArrowRight size={14} color="#ffffff" />
                </button>
              </form>
            </div>

            {/* СЕКЦИЯ КАРТОЧЕК С КНОПКОЙ КАТАЛОГА РЯДОМ */}
            <div className="section-header-row">
              <div>
                <h3 className="section-title">Карточки на сегодня ({morningWidgets.length})</h3>
                <span className="sub-text">Собрано под контекст дня</span>
              </div>
              <button className="btn-catalog-pill" onClick={() => setView('catalog')}>
                <span>Весь каталог (12)</span>
                <ArrowRight size={13} color="#f9f9f9" />
              </button>
            </div>

            {/* СЕТКА ВИДЖЕТОВ: ДВА МАЛЕНЬКИХ ВИДЖЕТА ВСЕГДА В ОДНУ СТРОКУ */}
            <div className="grid-cards-dense">
              {morningWidgets.map((w) => (
                <div key={w.id} className={`ui-card ${w.size === 'full' ? 'span-2' : ''}`}>
                  <div className="card-top-bar">
                    <span className="icon-wrap">{w.icon}</span>
                    <span className="card-tag">{w.tag}</span>
                  </div>
                  {w.render()}
                </div>
              ))}
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
                <span>Ассистент</span>
              </div>
            </div>

            {/* ПОТОК СООБЩЕНИЙ */}
            <div className="chat-flow">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`msg-bubble ${m.sender === 'user' ? 'msg-user' : 'msg-agent'}`}
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
                    className={`context-pill ${activeScenarioId === sc.id ? 'active' : ''}`}
                    onClick={() => {
                      handleScenarioChange(sc.id);
                      setMessages((prev) => [
                        ...prev,
                        { sender: 'user', text: `Контекст: ${sc.title}` },
                        { sender: 'agent', text: sc.agentGreeting }
                      ]);
                    }}
                  >
                    {sc.title}
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
              <button type="submit" className="btn-send-glass" aria-label="Отправить">
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
              <span className="pill pill-glass">Каталог A2UI (12)</span>
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
              {filteredCatalog.map((w) => (
                <div key={w.id} className={`ui-card ${w.size === 'full' ? 'span-2' : ''}`}>
                  <div className="card-top-bar">
                    <span className="icon-wrap">{w.icon}</span>
                    <span className="card-tag">{w.tag}</span>
                  </div>
                  {w.render()}
                </div>
              ))}
            </div>
          </main>
        )}
      </div>
    </div>
  );
}
