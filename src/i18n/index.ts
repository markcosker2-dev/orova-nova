import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import {
    SUPPORTED_LANGUAGE_CODES,
    resolveSupportedLanguage,
    type LanguageCode,
} from '../../shared/language';

// EN
import enCommon from './locales/en/common.json';
import enSettings from './locales/en/settings.json';
import enDashboard from './locales/en/dashboard.json';
import enChat from './locales/en/chat.json';
import enChannels from './locales/en/channels.json';
import enAgents from './locales/en/agents.json';
import enSkills from './locales/en/skills.json';
import enCron from './locales/en/cron.json';
import enSetup from './locales/en/setup.json';

// ZH
import zhCommon from './locales/zh/common.json';
import zhSettings from './locales/zh/settings.json';
import zhDashboard from './locales/zh/dashboard.json';
import zhChat from './locales/zh/chat.json';
import zhChannels from './locales/zh/channels.json';
import zhAgents from './locales/zh/agents.json';
import zhSkills from './locales/zh/skills.json';
import zhCron from './locales/zh/cron.json';
import zhSetup from './locales/zh/setup.json';

// JA
import jaCommon from './locales/ja/common.json';
import jaSettings from './locales/ja/settings.json';
import jaDashboard from './locales/ja/dashboard.json';
import jaChat from './locales/ja/chat.json';
import jaChannels from './locales/ja/channels.json';
import jaAgents from './locales/ja/agents.json';
import jaSkills from './locales/ja/skills.json';
import jaCron from './locales/ja/cron.json';
import jaSetup from './locales/ja/setup.json';

// RU
import ruCommon from './locales/ru/common.json';
import ruSettings from './locales/ru/settings.json';
import ruDashboard from './locales/ru/dashboard.json';
import ruChat from './locales/ru/chat.json';
import ruChannels from './locales/ru/channels.json';
import ruAgents from './locales/ru/agents.json';
import ruSkills from './locales/ru/skills.json';
import ruCron from './locales/ru/cron.json';
import ruSetup from './locales/ru/setup.json';

// ES
import esCommon from './locales/es/common.json';
import esSettings from './locales/es/settings.json';
import esDashboard from './locales/es/dashboard.json';
import esChat from './locales/es/chat.json';
import esChannels from './locales/es/channels.json';
import esAgents from './locales/es/agents.json';
import esSkills from './locales/es/skills.json';
import esCron from './locales/es/cron.json';
import esSetup from './locales/es/setup.json';

// HI
import hiCommon from './locales/hi/common.json';
import hiSettings from './locales/hi/settings.json';
import hiDashboard from './locales/hi/dashboard.json';
import hiChat from './locales/hi/chat.json';
import hiChannels from './locales/hi/channels.json';
import hiAgents from './locales/hi/agents.json';
import hiSkills from './locales/hi/skills.json';
import hiCron from './locales/hi/cron.json';
import hiSetup from './locales/hi/setup.json';

// AR
import arCommon from './locales/ar/common.json';
import arSettings from './locales/ar/settings.json';
import arDashboard from './locales/ar/dashboard.json';
import arChat from './locales/ar/chat.json';
import arChannels from './locales/ar/channels.json';
import arAgents from './locales/ar/agents.json';
import arSkills from './locales/ar/skills.json';
import arCron from './locales/ar/cron.json';
import arSetup from './locales/ar/setup.json';

// PT
import ptCommon from './locales/pt/common.json';
import ptSettings from './locales/pt/settings.json';
import ptDashboard from './locales/pt/dashboard.json';
import ptChat from './locales/pt/chat.json';
import ptChannels from './locales/pt/channels.json';
import ptAgents from './locales/pt/agents.json';
import ptSkills from './locales/pt/skills.json';
import ptCron from './locales/pt/cron.json';
import ptSetup from './locales/pt/setup.json';

// FR
import frCommon from './locales/fr/common.json';
import frSettings from './locales/fr/settings.json';
import frDashboard from './locales/fr/dashboard.json';
import frChat from './locales/fr/chat.json';
import frChannels from './locales/fr/channels.json';
import frAgents from './locales/fr/agents.json';
import frSkills from './locales/fr/skills.json';
import frCron from './locales/fr/cron.json';
import frSetup from './locales/fr/setup.json';

// DE
import deCommon from './locales/de/common.json';
import deSettings from './locales/de/settings.json';
import deDashboard from './locales/de/dashboard.json';
import deChat from './locales/de/chat.json';
import deChannels from './locales/de/channels.json';
import deAgents from './locales/de/agents.json';
import deSkills from './locales/de/skills.json';
import deCron from './locales/de/cron.json';
import deSetup from './locales/de/setup.json';

export const SUPPORTED_LANGUAGES = [
    { code: 'en', label: 'English' },
    { code: 'zh', label: '中文' },
    { code: 'ja', label: '日本語' },
    { code: 'ru', label: 'Русский' },
    { code: 'es', label: 'Español' },
    { code: 'hi', label: 'हिन्दी' },
    { code: 'ar', label: 'العربية' },
    { code: 'pt', label: 'Português' },
    { code: 'fr', label: 'Français' },
    { code: 'de', label: 'Deutsch' },
] as const satisfies ReadonlyArray<{ code: LanguageCode; label: string }>;

const resources = {
    en: {
        common: enCommon,
        settings: enSettings,
        dashboard: enDashboard,
        chat: enChat,
        channels: enChannels,
        agents: enAgents,
        skills: enSkills,
        cron: enCron,
        setup: enSetup,
    },
    zh: {
        common: zhCommon,
        settings: zhSettings,
        dashboard: zhDashboard,
        chat: zhChat,
        channels: zhChannels,
        agents: zhAgents,
        skills: zhSkills,
        cron: zhCron,
        setup: zhSetup,
    },
    ja: {
        common: jaCommon,
        settings: jaSettings,
        dashboard: jaDashboard,
        chat: jaChat,
        channels: jaChannels,
        agents: jaAgents,
        skills: jaSkills,
        cron: jaCron,
        setup: jaSetup,
    },
    ru: {
        common: ruCommon,
        settings: ruSettings,
        dashboard: ruDashboard,
        chat: ruChat,
        channels: ruChannels,
        agents: ruAgents,
        skills: ruSkills,
        cron: ruCron,
        setup: ruSetup,
    },
    es: {
        common: esCommon,
        settings: esSettings,
        dashboard: esDashboard,
        chat: esChat,
        channels: esChannels,
        agents: esAgents,
        skills: esSkills,
        cron: esCron,
        setup: esSetup,
    },
    hi: {
        common: hiCommon,
        settings: hiSettings,
        dashboard: hiDashboard,
        chat: hiChat,
        channels: hiChannels,
        agents: hiAgents,
        skills: hiSkills,
        cron: hiCron,
        setup: hiSetup,
    },
    ar: {
        common: arCommon,
        settings: arSettings,
        dashboard: arDashboard,
        chat: arChat,
        channels: arChannels,
        agents: arAgents,
        skills: arSkills,
        cron: arCron,
        setup: arSetup,
    },
    pt: {
        common: ptCommon,
        settings: ptSettings,
        dashboard: ptDashboard,
        chat: ptChat,
        channels: ptChannels,
        agents: ptAgents,
        skills: ptSkills,
        cron: ptCron,
        setup: ptSetup,
    },
    fr: {
        common: frCommon,
        settings: frSettings,
        dashboard: frDashboard,
        chat: frChat,
        channels: frChannels,
        agents: frAgents,
        skills: frSkills,
        cron: frCron,
        setup: frSetup,
    },
    de: {
        common: deCommon,
        settings: deSettings,
        dashboard: deDashboard,
        chat: deChat,
        channels: deChannels,
        agents: deAgents,
        skills: deSkills,
        cron: deCron,
        setup: deSetup,
    },
};

i18n
    .use(initReactI18next)
    .init({
        resources,
        lng: resolveSupportedLanguage(typeof navigator !== 'undefined' ? navigator.language : undefined),
        fallbackLng: 'en',
        supportedLngs: [...SUPPORTED_LANGUAGE_CODES],
        defaultNS: 'common',
        ns: ['common', 'settings', 'dashboard', 'chat', 'channels', 'agents', 'skills', 'cron', 'setup'],
        interpolation: {
            escapeValue: false, // React already escapes
        },
        react: {
            useSuspense: false,
        },
    });

export default i18n;
