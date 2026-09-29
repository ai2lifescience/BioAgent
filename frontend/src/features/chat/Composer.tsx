import { useLayoutEffect, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent, RefObject } from 'react';
import type { ModelOption } from '../../types';
import { LineIcon } from '../../components/icons';

export interface ComposerProps {
  models: ModelOption[];
  prompt: string;
  onPromptChange: (value: string) => void;
  fileCount?: number;
  running?: boolean;
  disabled?: boolean;
  model: string;
  turns: number;
  onModelChange: (value: string) => void;
  onTurnsChange: (value: number) => void;
  onSubmit: () => void | Promise<void>;
  onStop: () => void | Promise<void>;
  onAttach?: () => void;
  textareaRef?: RefObject<HTMLTextAreaElement | null>;
}

function Icon({ name }: { name: 'clip' | 'arrow' }) {
  return <LineIcon name={name} />;
}

function modelLabel(option: ModelOption) { return `${option.label || option.key}${option.cost_tier ? ` (${option.cost_tier})` : ''}`; }

export function Composer({
  models, prompt, onPromptChange, fileCount = 0, running = false, disabled = false, model, turns,
  onModelChange, onTurnsChange, onSubmit, onStop, onAttach, textareaRef,
}: ComposerProps) {
  const localRef = useRef<HTMLTextAreaElement>(null);
  const ref = textareaRef || localRef;
  const [composing, setComposing] = useState(false);
  const locked = disabled || running;
  useLayoutEffect(() => {
    const element = ref.current; if (!element) return;
    element.style.height = 'auto';
    element.style.height = `${Math.min(Math.max(element.scrollHeight, 96), 240)}px`;
  }, [prompt, ref]);
  const submit = (event?: FormEvent) => { event?.preventDefault(); if (!locked && prompt.trim()) void onSubmit(); };
  const keyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || composing || event.nativeEvent.isComposing || locked) return;
    event.preventDefault(); submit();
  };
  return <form className="composer" onSubmit={submit} aria-busy={running}>
    <textarea ref={ref} value={prompt} rows={2} disabled={locked} placeholder="Ask Pipeline2Agent… (attach data when needed)" aria-label="Message Pipeline2Agent" onChange={event => onPromptChange(event.target.value)} onKeyDown={keyDown} onCompositionStart={() => setComposing(true)} onCompositionEnd={() => setComposing(false)} />
    <div className="composer-toolbar"><div className="composer-left"><button className="attach-button" type="button" disabled={locked} onClick={onAttach} aria-label="Attach files"><Icon name="clip" /></button><span className="file-hint">{fileCount ? `${fileCount} file${fileCount === 1 ? '' : 's'} attached` : 'Add files'}</span><div className="settings"><label>Model<select value={model} disabled={locked} onChange={event => onModelChange(event.target.value)} aria-label="Model">{models.map(option => <option value={option.key} key={option.key}>{modelLabel(option)}</option>)}</select></label><label className="turns">Turns<input type="number" min={1} max={100} value={turns} disabled={locked} onChange={event => onTurnsChange(Math.max(1, Math.min(100, Number(event.target.value) || 1)))} aria-label="Maximum turns" /></label></div></div><div className="composer-right"><span className="shortcut">Enter to send · Shift + Enter for a new line</span>{running ? <button id="send" className="send-button stop" type="button" onClick={() => void onStop()} aria-label="Stop current request"><span className="stop-glyph" /></button> : <button id="send" className="send-button" type="submit" disabled={locked} aria-label="Send message"><Icon name="arrow" /></button>}</div></div>
  </form>;
}

export { Composer as ChatComposer };
