'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, ArrowRight, CalendarClock, Crosshair, FlaskConical, Power, RefreshCw, ShieldCheck, Target } from 'lucide-react'

import { BACKEND } from '@/lib/backend'

const HEALTH = {
  achieved: { label: 'ACHIEVED', color: '#34d399' },
  on_track: { label: 'ON TRACK', color: '#5b9bff' },
  at_risk: { label: 'AT RISK', color: '#f59e0b' },
  off_track: { label: 'OFF TRACK', color: '#ef6464' },
  missed: { label: 'MISSED', color: '#ef6464' },
}

function moneyLike(unit, value) {
  const number = Number(value || 0)
  if (['usd', 'cad', '$', 'mrr', 'arr'].includes((unit || '').toLowerCase())) {
    return new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', maximumFractionDigits: 0 }).format(number)
  }
  return `${new Intl.NumberFormat('en-CA', { maximumFractionDigits: 1 }).format(number)} ${unit || ''}`.trim()
}

function defaultDeadline() {
  const date = new Date()
  date.setMonth(date.getMonth() + 8)
  return date.toISOString().slice(0, 10)
}

export default function GoalCommandCenter({ userId, onAskRue }) {
  const [snapshot, setSnapshot] = useState(null)
  const [configured, setConfigured] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [metricValue, setMetricValue] = useState('')
  const [autonomy, setAutonomy] = useState(null)
  const [policySaving, setPolicySaving] = useState(false)
  const [form, setForm] = useState({
    objective: 'Reach $30,000 MRR',
    metric_key: 'monthly_recurring_revenue',
    unit: 'cad',
    baseline_value: '0',
    current_value: '0',
    target_value: '30000',
    deadline: defaultDeadline(),
    constraints: '',
  })

  const load = useCallback(async () => {
    if (!userId) return
    setError('')
    try {
      const response = await fetch(`${BACKEND}/api/business/goals/command-center?user_id=${encodeURIComponent(userId)}`)
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Goal Engine is unavailable')
      setSnapshot(data.snapshot || null)
      setConfigured(!!data.configured)
      const current = data.snapshot?.goal?.current_value
      if (current != null) setMetricValue(String(current))
      try {
        const autonomyResponse = await fetch(`${BACKEND}/api/business/runtime/autonomy?user_id=${encodeURIComponent(userId)}`)
        if (autonomyResponse.ok) setAutonomy(await autonomyResponse.json())
      } catch (_) {
        // Runtime migrations roll out independently; Goal Engine remains usable.
      }
    } catch (exc) {
      setError(exc.message || 'Could not load Goal Engine')
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => { load() }, [load])

  const createGoal = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const response = await fetch(`${BACKEND}/api/business/goals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          objective: form.objective,
          metric_key: form.metric_key,
          unit: form.unit,
          direction: 'increase',
          baseline_value: Number(form.baseline_value),
          current_value: Number(form.current_value),
          target_value: Number(form.target_value),
          deadline: new Date(`${form.deadline}T23:59:59`).toISOString(),
          constraints: form.constraints.split('\n').map(v => v.trim()).filter(Boolean),
          leading_indicators: [],
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not create goal')
      setShowForm(false)
      await load()
    } catch (exc) {
      setError(exc.message || 'Could not create goal')
    } finally {
      setSaving(false)
    }
  }

  const recordProgress = async () => {
    const goal = snapshot?.goal
    if (!goal || metricValue === '') return
    setSaving(true)
    setError('')
    try {
      const response = await fetch(`${BACKEND}/api/business/goals/${goal.id}/observations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          value: Number(metricValue),
          source_type: 'manual',
          idempotency_key: `manual:${goal.id}:${Date.now()}`,
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not record progress')
      await load()
    } catch (exc) {
      setError(exc.message || 'Could not record progress')
    } finally {
      setSaving(false)
    }
  }

  const toggleKillSwitch = async () => {
    if (!autonomy) return
    setPolicySaving(true)
    setError('')
    try {
      const response = await fetch(`${BACKEND}/api/business/runtime/autonomy`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, kill_switch: !autonomy.policy?.kill_switch }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not update autonomy')
      setAutonomy(current => ({ ...current, policy: data.policy }))
    } catch (exc) {
      setError(exc.message || 'Could not update autonomy')
    } finally {
      setPolicySaving(false)
    }
  }

  const goal = snapshot?.goal
  const health = goal?.health || {}
  const healthStyle = HEALTH[health.health] || HEALTH.at_risk
  const counts = snapshot?.initiative_counts || {}
  const activeInitiatives = useMemo(
    () => Object.entries(counts).filter(([key]) => !['succeeded', 'failed', 'cancelled'].includes(key)).reduce((sum, [, value]) => sum + value, 0),
    [counts]
  )
  const latestExperiment = snapshot?.experiments?.[0]

  if (loading) {
    return (
      <div style={{ height: 116, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, background: '#131316', marginBottom: 16, display: 'grid', placeItems: 'center' }}>
        <span className='font-pixel' style={{ color: 'var(--os1-text-faint)', fontSize: 10 }}>Loading Goal Engine…</span>
      </div>
    )
  }

  if (!configured) {
    return (
      <div style={{ border: '1px solid rgba(45,127,249,0.22)', borderRadius: 14, background: 'linear-gradient(135deg, rgba(45,127,249,0.08), #131316 45%)', padding: 16, marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ width: 38, height: 38, borderRadius: 11, display: 'grid', placeItems: 'center', background: 'rgba(45,127,249,0.13)', color: '#5b9bff' }}><Crosshair size={19} /></div>
            <div>
              <div className='font-pixel' style={{ color: '#f5f5f4', fontSize: 12 }}>Give Rue an outcome, not a prompt</div>
              <div className='os1-serif-micro' style={{ color: '#858583', fontSize: 10, marginTop: 4 }}>This becomes the durable objective every Operator cycle measures and pursues.</div>
            </div>
          </div>
          <button onClick={() => setShowForm(v => !v)} className='font-pixel' style={{ border: '1px solid rgba(45,127,249,0.35)', background: 'rgba(45,127,249,0.12)', color: '#75a8ff', borderRadius: 9, padding: '8px 12px', fontSize: 10, cursor: 'pointer' }}>
            {showForm ? 'Close' : 'Set operating goal'}
          </button>
        </div>
        {showForm && (
          <form onSubmit={createGoal} style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid rgba(255,255,255,0.07)', display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 10 }}>
            <label style={{ gridColumn: '1 / -1' }}><span className='os1-serif-micro goal-label'>Outcome</span><input required value={form.objective} onChange={e => setForm({ ...form, objective: e.target.value })} className='goal-input' /></label>
            <label><span className='os1-serif-micro goal-label'>Metric key</span><input required value={form.metric_key} onChange={e => setForm({ ...form, metric_key: e.target.value.replace(/\s+/g, '_').toLowerCase() })} className='goal-input' /></label>
            <label><span className='os1-serif-micro goal-label'>Current</span><input type='number' required value={form.current_value} onChange={e => setForm({ ...form, current_value: e.target.value, baseline_value: e.target.value })} className='goal-input' /></label>
            <label><span className='os1-serif-micro goal-label'>Target</span><input type='number' required value={form.target_value} onChange={e => setForm({ ...form, target_value: e.target.value })} className='goal-input' /></label>
            <label><span className='os1-serif-micro goal-label'>Unit</span><input required value={form.unit} onChange={e => setForm({ ...form, unit: e.target.value })} className='goal-input' /></label>
            <label><span className='os1-serif-micro goal-label'>Deadline</span><input type='date' required value={form.deadline} onChange={e => setForm({ ...form, deadline: e.target.value })} className='goal-input' /></label>
            <label><span className='os1-serif-micro goal-label'>Constraints (one per line)</span><input value={form.constraints} onChange={e => setForm({ ...form, constraints: e.target.value })} placeholder='Max $4k monthly spend' className='goal-input' /></label>
            <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span className='os1-serif-micro' style={{ color: '#ef6464', fontSize: 9 }}>{error}</span>
              <button disabled={saving} className='font-pixel' style={{ border: 0, background: '#2d7ff9', color: 'white', borderRadius: 9, padding: '9px 14px', fontSize: 10, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}>{saving ? 'Creating…' : 'Activate goal'}</button>
            </div>
            <style>{`.goal-label{display:block;color:#777775;font-size:9px;margin-bottom:5px}.goal-input{width:100%;box-sizing:border-box;background:#0d0d0f;border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:9px 10px;color:#ececea;font-size:12px;outline:none}.goal-input:focus{border-color:rgba(45,127,249,.55)}`}</style>
          </form>
        )}
        {!showForm && error && <div className='os1-serif-micro' style={{ color: '#ef6464', fontSize: 9, marginTop: 10 }}>{error}</div>}
      </div>
    )
  }

  const progress = Math.max(0, Math.min(100, Number(health.progress_percent || 0)))
  return (
    <div style={{ border: '1px solid rgba(255,255,255,0.09)', borderRadius: 14, background: '#131316', marginBottom: 16, overflow: 'hidden' }}>
      <div style={{ padding: '14px 16px 13px', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 18 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7 }}>
            <Target size={14} style={{ color: '#5b9bff' }} />
            <span className='font-pixel' style={{ fontSize: 9, letterSpacing: '.08em', color: '#777775' }}>ACTIVE OPERATING GOAL</span>
            <span className='font-pixel' style={{ fontSize: 8, color: healthStyle.color, border: `1px solid ${healthStyle.color}55`, borderRadius: 999, padding: '2px 7px', background: `${healthStyle.color}12` }}>{healthStyle.label}</span>
          </div>
          <div className='font-pixel' style={{ fontSize: 15, color: '#f5f5f4', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{goal.objective}</div>
          <div style={{ height: 6, borderRadius: 999, background: 'rgba(255,255,255,0.06)', marginTop: 12, overflow: 'hidden' }}>
            <div style={{ width: `${progress}%`, height: '100%', borderRadius: 999, background: healthStyle.color, boxShadow: `0 0 14px ${healthStyle.color}55`, transition: 'width .4s ease' }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
            <span className='os1-serif-micro' style={{ fontSize: 9, color: '#858583' }}>{moneyLike(goal.unit, goal.current_value)} current</span>
            <span className='os1-serif-micro' style={{ fontSize: 9, color: '#858583' }}>{moneyLike(goal.unit, goal.target_value)} target · {progress}%</span>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(92px, 1fr))', gap: 8 }}>
          <MiniMetric icon={<CalendarClock size={13} />} label='TIME LEFT' value={`${health.remaining_days} days`} />
          <MiniMetric icon={<Activity size={13} />} label='DAILY PACE' value={moneyLike(goal.unit, health.required_daily_change)} />
          <MiniMetric
            icon={latestExperiment ? <FlaskConical size={13} /> : <Crosshair size={13} />}
            label={latestExperiment ? 'LATEST TEST' : 'INITIATIVES'}
            value={latestExperiment ? String(latestExperiment.status || 'running').toUpperCase() : String(activeInitiatives)}
          />
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid rgba(255,255,255,0.06)', background: '#101012', padding: '8px 12px 8px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className='os1-serif-micro' style={{ fontSize: 9, color: '#747472' }}>Record actual {goal.metric_key.replace(/_/g, ' ')}</span>
          <input type='number' value={metricValue} onChange={e => setMetricValue(e.target.value)} style={{ width: 100, background: '#09090a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 7, padding: '6px 8px', color: '#e8e8e6', fontSize: 11 }} />
          <button disabled={saving} onClick={recordProgress} className='font-pixel' style={{ border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.04)', color: '#b8b8b6', borderRadius: 7, padding: '6px 9px', fontSize: 8, cursor: 'pointer' }}>{saving ? 'Saving…' : 'Update'}</button>
          {error && <span className='os1-serif-micro' style={{ color: '#ef6464', fontSize: 8 }}>{error}</span>}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {autonomy && (
            <div className='font-pixel' title='Autonomous Operator capacity this month' style={{ display: 'flex', alignItems: 'center', gap: 5, color: autonomy.policy?.kill_switch ? '#ef6464' : '#8daee3', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '0 8px', fontSize: 7 }}>
              <ShieldCheck size={11} /> {autonomy.monthly_runs_remaining}/{autonomy.monthly_run_limit} RUNS
            </div>
          )}
          {autonomy && (
            <button
              onClick={toggleKillSwitch}
              disabled={policySaving}
              title={autonomy.policy?.kill_switch ? 'Resume autonomous work' : 'Emergency stop: pause every autonomous workflow'}
              className='font-pixel'
              style={{ display: 'flex', alignItems: 'center', gap: 5, border: `1px solid ${autonomy.policy?.kill_switch ? 'rgba(52,211,153,.3)' : 'rgba(239,100,100,.25)'}`, background: autonomy.policy?.kill_switch ? 'rgba(52,211,153,.08)' : 'rgba(239,100,100,.06)', color: autonomy.policy?.kill_switch ? '#65d8aa' : '#df7b7b', borderRadius: 8, padding: '6px 9px', fontSize: 7, cursor: 'pointer', opacity: policySaving ? 0.5 : 1 }}
            >
              <Power size={10} /> {autonomy.policy?.kill_switch ? 'RESUME RUE' : 'PAUSE RUE'}
            </button>
          )}
          <button onClick={load} title='Refresh goal state' className='os1-iconbtn' style={{ width: 28, height: 28 }}><RefreshCw size={13} /></button>
          <button onClick={() => onAskRue?.(`Analyze our progress toward: ${goal.objective}. Identify the single biggest bottleneck and tell me what initiative you should execute next.`)} className='font-pixel' style={{ display: 'flex', alignItems: 'center', gap: 6, border: '1px solid rgba(45,127,249,0.28)', background: 'rgba(45,127,249,0.09)', color: '#75a8ff', borderRadius: 8, padding: '6px 10px', fontSize: 8, cursor: 'pointer' }}>Ask Rue for next move <ArrowRight size={11} /></button>
        </div>
      </div>
    </div>
  )
}

function MiniMetric({ icon, label, value }) {
  return (
    <div style={{ minWidth: 0, border: '1px solid rgba(255,255,255,0.065)', borderRadius: 10, background: '#0e0e10', padding: '9px 10px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#686866' }}>{icon}<span className='font-pixel' style={{ fontSize: 7 }}>{label}</span></div>
      <div className='font-pixel' style={{ marginTop: 7, color: '#d8d8d6', fontSize: 10, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{value}</div>
    </div>
  )
}
