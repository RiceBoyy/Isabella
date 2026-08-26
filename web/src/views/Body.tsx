import { useEffect, useState } from "react";
import { api, ApiError, type BodyLog } from "../api";
import { Body3D, type LayerInfo, type Tone } from "../components/Body3D";

/**
 * Owen's body. The model, and nothing else on the screen.
 *
 * `health` is hers; this is his. Three layers ship in `public/anatomy` -
 * skin, muscle, skeleton - and `skeleton` in the palette switches to it. With
 * no atlas installed the component falls back to built-in primitives and still
 * works, which is why the fallback exists.
 *
 * Regions light only from an exercise **actually ticked** in this week's log.
 * An untouched week lights nothing rather than showing a body with a story on
 * it. The numbers behind it are still served at `GET /body`; they are not drawn
 * here, because the model is the screen.
 *
 * The credit is not decoration. The muscle and skeleton meshes are Z-Anatomy
 * under CC BY-SA 4.0, which requires attribution to be visible where the work
 * is seen rather than buried in a README - so the component reports it and
 * this prints it.
 */

export function Body({
  layer,
  onLayers,
}: {
  layer: string | null;
  onLayers: (layers: LayerInfo[], fallback: string) => void;
}) {
  const [log, setLog] = useState<BodyLog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [credit, setCredit] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .body()
      .then((data) => live && setLog(data))
      .catch((cause: ApiError) => live && setError(cause.message));
    return () => {
      live = false;
    };
  }, []);

  /* A bare group id lights both sides - the model resolves `chest` to chest.l
     and chest.r itself, so the reader's ids need no translation. */
  const active: Record<string, Tone> = Object.fromEntries(
    (log?.week.worked ?? []).map((group) => [group, "worked" as Tone]),
  );

  return (
    <div className="stage">
      {(log?.week.worked.length ?? 0) > 0 && <div className="stage__glow" />}

      {/* Mounted regardless of the log: the scene builds once, and waiting for
          the fetch would tear it down and rebuild it when the data landed. */}
      <Body3D active={active} layer={layer} onLayers={onLayers} onCredit={setCredit} />

      <div className="stage__note">
        {error && <span className="notice--bad">{error}</span>}
        {log && !log.available && <span>{log.detail}</span>}
        {log?.available && !log.week.logged && <span>nothing ticked in {log.week.key}</span>}
      </div>

      {credit && <span className="stage__credit">{credit}</span>}
    </div>
  );
}
