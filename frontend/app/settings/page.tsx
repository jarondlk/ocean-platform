"use client";

import { Check, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";

import { useAppPreferences, type Accent, type Density, type SidebarMode, type ThemeMode } from "@/lib/preferences";

export default function SettingsPage() {
  const { preferences, setPreference, resetPreferences, t } = useAppPreferences();

  function reset() {
    resetPreferences();
  }

  return (
    <section className="settings-page">
      <header className="page-header">
        <h2>{t("settings", "title")}</h2>
      </header>

      <div className="settings-layout">
        <div className="settings-main-column">
          <SettingsSection title={t("settings", "appearance")}>
            <fieldset className="settings-choice-fieldset">
              <legend>{t("settings", "theme")}</legend>
              <div className="choice-grid three-up">
                {(["light", "dark", "system"] as ThemeMode[]).map((theme) => (
                  <ChoiceCard
                    key={theme}
                    active={preferences.theme === theme}
                    label={t("settings", theme)}
                    onClick={() => setPreference("theme", theme)}
                  />
                ))}
              </div>
            </fieldset>

            <fieldset className="settings-choice-fieldset">
              <legend>{t("settings", "language")}</legend>
              <div className="choice-grid two-up">
                <ChoiceCard active={preferences.locale === "en"} label={t("settings", "english")} onClick={() => setPreference("locale", "en")} />
                <ChoiceCard active={preferences.locale === "ja"} label={t("settings", "japanese")} onClick={() => setPreference("locale", "ja")} />
              </div>
            </fieldset>
          </SettingsSection>

          <SettingsSection title={t("settings", "interface")}>
            <PreferenceSelect
              label={t("settings", "density")}
              value={preferences.density}
              options={[
                ["comfortable", t("settings", "comfortable")],
                ["compact", t("settings", "compact")],
              ]}
              onChange={(value) => setPreference("density", value as Density)}
            />
            <PreferenceSelect
              label={t("settings", "sidebar")}
              value={preferences.sidebar}
              options={[
                ["expanded", t("settings", "expanded")],
                ["compact", t("settings", "narrow")],
              ]}
              onChange={(value) => setPreference("sidebar", value as SidebarMode)}
            />
            <PreferenceSelect
              label={t("settings", "accent")}
              value={preferences.accent}
              options={[
                ["ocean", t("settings", "ocean")],
                ["violet", t("settings", "violet")],
                ["amber", t("settings", "amber")],
              ]}
              onChange={(value) => setPreference("accent", value as Accent)}
            />
            <label className="preference-toggle">
              <input
                type="checkbox"
                checked={preferences.reducedMotion}
                onChange={(event) => setPreference("reducedMotion", event.target.checked)}
              />
              <span>
                <strong>{t("settings", "reducedMotion")}</strong>
              </span>
            </label>
          </SettingsSection>

          <div className="settings-actions">
            <button className="button secondary-button" type="button" onClick={reset}>
              <RotateCcw size={15} aria-hidden="true" />
              {t("settings", "reset")}
            </button>
          </div>
        </div>

        <aside className="settings-preview" aria-label={t("settings", "preview")}>
          <div className="settings-preview-heading">
            <h3 className="section-title">{t("settings", "preview")}</h3>
            <span className="status-pill"><Check size={13} aria-hidden="true" /> {t("settings", "active")}</span>
          </div>
          <div className="preview-window">
            <div className="preview-window-bar"><span /><span /><span /></div>
            <div className="preview-window-body">
              <div className="preview-lines"><span /><span /><span /></div>
              <div className="preview-chip-row"><i /><i /><i /></div>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}

function SettingsSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="settings-panel">
      <div className="settings-panel-heading">
        <h3 className="section-title">{title}</h3>
      </div>
      <div className="settings-panel-body">{children}</div>
    </section>
  );
}

function ChoiceCard({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button className={`choice-card${active ? " active" : ""}`} type="button" onClick={onClick} aria-pressed={active}>
      <span className="choice-card-indicator">{active ? <Check size={14} aria-hidden="true" /> : null}</span>
      <strong>{label}</strong>
    </button>
  );
}

function PreferenceSelect({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (value: string) => void }) {
  return (
    <label className="settings-field preference-select">
      <span>{label}</span>
      <select className="field" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}
      </select>
    </label>
  );
}
