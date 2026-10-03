import { FormEvent, useState } from 'react';

export type Persona = 'owner' | 'contractor_maya' | 'contractor_leo';

export interface Session {
  principal_id: string;
  effective_user_id: string;
  agency_id: string;
  role: 'owner' | 'contractor';
  recipient_ref: 'contractor_maya' | 'contractor_leo' | null;
  is_judge: boolean;
  csrf_token: string;
  expires_at: string;
}

export async function messageFor(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data.message || data.detail?.message || `Request failed (${response.status}).`;
  } catch {
    return `Request failed (${response.status}).`;
  }
}

export function SessionGate({ busy, error, onSignIn }: {
  busy: boolean;
  error: string | null;
  onSignIn: (code: string, persona: Persona) => Promise<void>;
}) {
  const [code, setCode] = useState('');
  const [persona, setPersona] = useState<Persona>('owner');
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void onSignIn(code, persona);
    setCode('');
  };
  return (
    <main className="session-page">
      <form className="session-card" onSubmit={submit}>
        <p className="session-brand">ProofPay</p>
        <h1>Workspace access</h1>
        <p>Enter the access code supplied for your workspace. Your code determines which personas you can use.</p>
        <label htmlFor="access-code">Access code</label>
        <input id="access-code" type="password" autoComplete="current-password" maxLength={256}
          required value={code} onChange={event => setCode(event.target.value)} />
        <label htmlFor="starting-persona">Starting persona</label>
        <select id="starting-persona" value={persona} onChange={event => setPersona(event.target.value as Persona)}>
          <option value="owner">Agency owner</option>
          <option value="contractor_maya">Contractor Maya</option>
          <option value="contractor_leo">Contractor Leo</option>
        </select>
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? 'Checking access…' : 'Enter workspace'}</button>
        <p className="session-note">Development preview: verification and payments are awaiting implementation.</p>
      </form>
    </main>
  );
}
