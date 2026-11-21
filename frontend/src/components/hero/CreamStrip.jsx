/* ============================================================
   CreamsStrip — Stats strip with S-Notch, stats, sprout
   ============================================================ */
import { SNotch }         from './SNotch.jsx';
import { BotanicalSprout } from './BotanicalSprout.jsx';

export function CreamStrip() {
  return (
    <section className="cream-strip" aria-label="Agent performance stats">
      {/* Curved S-Notch top edge */}
      <SNotch />

      {/* Scroll hint on the raised right plateau */}
      <span className="scroll-hint" aria-hidden="true">
        ↓&nbsp;Scroll to open workspace
      </span>

      {/* Strip body */}
      <div className="strip-content">
        {/* Lead text */}
        <p className="strip-lead">
          Zero&nbsp;hallucinations<br />
          from call to board
        </p>

        <div className="strip-divider" aria-hidden="true" />

        {/* Three stats */}
        <div className="strip-stats" role="list">
          {[
            { number: '100%',   label: 'Human-in-the-loop gated'       },
            { number: '< 2.4s', label: 'Cross-meeting conflict audit'   },
            { number: '0',      label: 'Invented owners or dates'       },
          ].map(({ number, label }) => (
            <div className="stat-item" key={label} role="listitem">
              <span className="stat-number">{number}</span>
              <span className="stat-label">{label}</span>
            </div>
          ))}
        </div>

        {/* Botanical sprout */}
        <BotanicalSprout size={56} />
      </div>
    </section>
  );
}
