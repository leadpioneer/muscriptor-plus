import { useEffect, useState, type RefObject } from "react";
import clsx from "clsx";
import type { AudioEngine } from "../audio";
import { useI18n } from "../i18n";
import { Button } from "./Button";
import { IconPlay, IconPause } from "./icons";

/** A labelled volume slider, 0..1. */
function VolumeSlider(props: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  const { label, value, onChange } = props;
  return (
    <label className="inline-flex items-center gap-2 text-sm text-muted">
      <span className="min-w-8 text-center">{label}</span>
      <input
        className="mix-slider"
        type="range"
        min="0"
        max="1"
        step="0.01"
        value={value}
        aria-label={label}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        // Drop focus once the drag ends so Space keeps toggling play/pause
        // (the global handler ignores Space while an input is focused).
        onPointerUp={(e) => e.currentTarget.blur()}
        onClick={(e) => e.currentTarget.blur()}
      />
    </label>
  );
}

export function Controls(props: {
  audio: AudioEngine;
  /** Attached to the time clock; updated imperatively by the rAF loop. */
  clockRef: RefObject<HTMLSpanElement | null>;
  /** Independent bus volumes (0..1 each) and the master output volume. */
  wavVol: number;
  onWavVolChange: (v: number) => void;
  midiVol: number;
  onMidiVolChange: (v: number) => void;
  masterVol: number;
  onMasterVolChange: (v: number) => void;
  stereo: boolean;
  onStereoChange: (v: boolean) => void;
  /** Whether the roll auto-follows the playhead (toggled off by manual scrolling). */
  following: boolean;
  onToggleFollow: () => void;
}) {
  const {
    audio,
    clockRef,
    wavVol,
    onWavVolChange,
    midiVol,
    onMidiVolChange,
    masterVol,
    onMasterVolChange,
    stereo,
    onStereoChange,
    following,
    onToggleFollow,
  } = props;
  const { t } = useI18n();
  // The transport's state isn't React state (and it can auto-stop at the end),
  // so poll it each frame to keep the toggle button's label in sync.
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      setPlaying(audio.state === "started");
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [audio]);

  return (
    <div className="col-span-full flex flex-wrap items-center gap-x-2.5 gap-y-2 rounded-card border border-line bg-surface px-3.5 py-3 animate-rise [animation-delay:0.06s]">
      <Button
        className={clsx(
          "inline-flex items-center gap-2",
          playing && "border-accent bg-accent text-white hover:border-accent hover:bg-accent",
        )}
        onClick={(e) => {
          e.currentTarget.blur();
          playing ? audio.pause() : audio.play();
        }}
      >
        {playing ? <IconPause /> : <IconPlay />}
        {playing ? t("pause") : t("play")}
      </Button>
      <Button
        className={clsx("text-content", following && "border-accent hover:border-accent")}
        aria-pressed={following}
        title={following ? t("follow_off_title") : t("follow_on_title")}
        onClick={(e) => {
          e.currentTarget.blur();
          onToggleFollow();
        }}
      >
        {t("follow_playhead")}
      </Button>
      <span
        className="rounded-md border border-line bg-bg px-2.5 py-1 font-mono text-sm tabular-nums text-muted"
        ref={clockRef}
      >
        0.0s
      </span>
      <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-2 max-[760px]:ml-0">
        <VolumeSlider label={t("volume_master")} value={masterVol} onChange={onMasterVolChange} />
        <VolumeSlider label={t("volume_original")} value={wavVol} onChange={onWavVolChange} />
        <VolumeSlider label={t("volume_midi")} value={midiVol} onChange={onMidiVolChange} />
        <label className="inline-flex cursor-pointer select-none items-center gap-1.5 text-sm text-muted px-3">
          <input
            className="cursor-pointer accent-accent"
            type="checkbox"
            checked={stereo}
            onChange={(e) => onStereoChange(e.target.checked)}
            // Same as the sliders: keep Space bound to play/pause after clicking.
            // click (not pointerup) also catches clicks on the wrapping label,
            // which the browser forwards to the checkbox.
            onClick={(e) => e.currentTarget.blur()}
          />
          <span>{t("stereo")}</span>
        </label>
      </div>
    </div>
  );
}
