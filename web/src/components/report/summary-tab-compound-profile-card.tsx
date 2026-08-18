"use client";

import { ExternalLink } from "lucide-react";
import { FunctionalGroupBadges } from "@/components/chemistry/functional-group-badges";
import { MoleculeViewer2D } from "@/components/chemistry/molecule-viewer-2d";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PUBCHEM_COMPOUND_URL } from "@/lib/constants";
import { cn, truncate } from "@/lib/utils";
import { CompoundSynonyms } from "@/components/report/summary-tab-compound-synonyms";
import type { FTOReport } from "@praviar/shared-types";

function SimilarityMeter({
  compoundName,
  similarity,
}: {
  compoundName: string;
  similarity: number;
}) {
  const percentage = Math.round(similarity * 100);

  return (
    <div className="flex min-w-0 items-center gap-2">
      <div
        className="h-1.5 min-w-16 flex-1 overflow-hidden rounded-full bg-[var(--surface-hover)]"
        role="progressbar"
        aria-label={`${compoundName} similarity`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percentage}
      >
        <div
          className="h-full rounded-full bg-[var(--brand-primary)]"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="w-9 shrink-0 text-right text-xs tabular-nums text-[var(--text-primary)]">
        {percentage}%
      </span>
    </div>
  );
}

function KeyValueRow({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="grid min-w-0 grid-cols-[7rem_minmax(0,1fr)] gap-3 border-b border-[var(--border-default)] py-1.5">
      <span className="text-sm text-[var(--text-secondary)]">{label}</span>
      <span
        className={cn(
          "min-w-0 text-right text-sm text-[var(--text-primary)] [overflow-wrap:anywhere]",
          valueClassName,
        )}
      >
        {value}
      </span>
    </div>
  );
}

const INPUT_TYPE_LABELS: Record<string, string> = {
  cas: "CAS number",
  inchi: "InChI",
  inchikey: "InChIKey",
  name: "Name",
  smiles: "SMILES",
};

function IdentityValue({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 break-all font-mono text-xs leading-5 text-[var(--text-primary)]">
        {value?.trim() || "Not emitted"}
      </dd>
    </div>
  );
}

function CompoundIdentityResolution({ report }: { report: FTOReport }) {
  const compound = report.compound;

  return (
    <section
      aria-labelledby="compound-identity-resolution-title"
      className="overflow-hidden rounded-lg border border-brand-primary/20 bg-[var(--surface-muted)]/35"
      data-testid="compound-identity-resolution"
    >
      <div className="border-b border-[var(--border-subtle)] px-3 py-3">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
          Identity resolution
        </p>
        <h3
          id="compound-identity-resolution-title"
          className="mt-1 text-sm font-semibold text-[var(--text-primary)]"
        >
          Submitted input → resolved identity → search variants
        </h3>
        <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
          The resolved structure is the pipeline identity. Broadened search
          forms extend retrieval and do not replace the submitted product form.
        </p>
      </div>

      <div className="grid divide-y divide-[var(--border-subtle)] lg:grid-cols-3 lg:divide-x lg:divide-y-0">
        <div className="min-w-0 space-y-3 p-3">
          <p className="text-xs font-semibold text-[var(--text-primary)]">
            1 · Submitted
          </p>
          <dl className="space-y-3">
            <IdentityValue
              label={INPUT_TYPE_LABELS[compound.input_type] ?? "Input"}
              value={compound.original_input}
            />
          </dl>
        </div>

        <div className="min-w-0 space-y-3 p-3">
          <p className="text-xs font-semibold text-[var(--text-primary)]">
            2 · Canonical resolution
          </p>
          <dl className="space-y-3">
            <IdentityValue label="Resolved name" value={compound.name} />
            <IdentityValue
              label="Canonical SMILES"
              value={compound.canonical_smiles}
            />
          </dl>
        </div>

        <div className="min-w-0 space-y-3 p-3">
          <p className="text-xs font-semibold text-[var(--text-primary)]">
            3 · Retrieval variants
          </p>
          <dl className="space-y-3">
            <IdentityValue
              label="Free-base search form"
              value={compound.free_base_smiles}
            />
            <IdentityValue
              label="Stereo-stripped search form"
              value={compound.stereo_stripped_smiles}
            />
          </dl>
          <p className="rounded-md border border-warning/25 bg-warning/10 px-2.5 py-2 text-xs leading-5 text-[var(--text-secondary)]">
            A separate tautomer-normalized structure is not emitted by the
            current report contract.
          </p>
        </div>
      </div>
    </section>
  );
}

export function CompoundProfileCard({ report }: { report: FTOReport }) {
  const compound = report.compound;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Compound Profile</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {compound.canonical_smiles ? (
          <div className="flex justify-center">
            <MoleculeViewer2D
              smiles={compound.canonical_smiles}
              width={320}
              height={240}
              label={compound.name}
            />
          </div>
        ) : null}
        <CompoundIdentityResolution report={report} />
        <div className="space-y-2">
          <KeyValueRow
            label="InChI Key"
            value={compound.inchi_key}
            valueClassName="font-mono text-xs"
          />
          <KeyValueRow label="Formula" value={compound.molecular_formula} />
          <KeyValueRow
            label="Molecular Weight"
            value={
              compound.molecular_weight != null
                ? `${compound.molecular_weight} Da`
                : "—"
            }
          />

          {compound.pubchem_cid != null ? (
            <div className="grid min-w-0 grid-cols-[7rem_minmax(0,1fr)] gap-3 border-b border-[var(--border-default)] py-1.5">
              <span className="text-sm text-[var(--text-secondary)]">
                PubChem CID
              </span>
              <a
                href={`${PUBCHEM_COMPOUND_URL}/${compound.pubchem_cid}`}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Open PubChem CID ${compound.pubchem_cid} in PubChem`}
                className="inline-flex min-h-11 min-w-0 items-center justify-end gap-1 rounded-md px-2.5 text-sm text-[var(--brand-primary)] transition-colors hover:bg-brand-primary/10 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
              >
                {compound.pubchem_cid}
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          ) : null}

          {compound.cas_numbers.length > 0 ? (
            <div className="grid min-w-0 grid-cols-[7rem_minmax(0,1fr)] items-start gap-3 border-b border-[var(--border-default)] py-1.5">
              <span className="text-sm text-[var(--text-secondary)]">CAS</span>
              <div className="flex flex-wrap justify-end gap-1">
                {compound.cas_numbers.map((cas) => (
                  <Badge
                    key={cas}
                    variant="secondary"
                    className="text-xs font-mono"
                  >
                    {cas}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}

          {compound.synonyms.length > 0 ? (
            <CompoundSynonyms synonyms={compound.synonyms} />
          ) : null}

          {compound.functional_groups.length > 0 ? (
            <div className="pt-1">
              <span className="mb-2 block text-sm text-[var(--text-secondary)]">
                Functional Groups
              </span>
              <FunctionalGroupBadges groups={compound.functional_groups} />
            </div>
          ) : null}

          {compound.related_compounds.length > 0 ? (
            <div className="pt-2">
              <span className="mb-2 block text-sm text-[var(--text-secondary)]">
                Related Compounds
              </span>

              <ul
                className="space-y-2 sm:hidden"
                aria-label="Related compounds"
              >
                {compound.related_compounds.map((relatedCompound) => (
                  <li
                    key={relatedCompound.cid}
                    className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-subtle)] p-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <span className="min-w-0 font-medium text-[var(--text-primary)]">
                        {relatedCompound.name ??
                          `PubChem CID ${relatedCompound.cid}`}
                      </span>
                      <Badge
                        variant="secondary"
                        className="shrink-0 text-xs tabular-nums"
                      >
                        {Math.round(relatedCompound.tanimoto_similarity * 100)}%
                        match
                      </Badge>
                    </div>
                    <code className="mt-2 block break-all text-xs leading-relaxed text-[var(--text-secondary)]">
                      {truncate(relatedCompound.canonical_smiles, 48)}
                    </code>
                    <div className="mt-3">
                      <SimilarityMeter
                        compoundName={
                          relatedCompound.name ??
                          `PubChem CID ${relatedCompound.cid}`
                        }
                        similarity={relatedCompound.tanimoto_similarity}
                      />
                    </div>
                  </li>
                ))}
              </ul>

              <div
                className="hidden overflow-x-auto focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] sm:block"
                role="region"
                tabIndex={0}
                aria-label="Related compounds horizontal scroll area"
              >
                <table className="w-full min-w-[28rem] text-xs">
                  <thead>
                    <tr className="border-b border-[var(--border-default)]">
                      <th
                        scope="col"
                        className="py-1.5 text-left font-semibold uppercase tracking-wider text-[var(--text-tertiary)]"
                      >
                        Name
                      </th>
                      <th
                        scope="col"
                        className="py-1.5 text-left font-semibold uppercase tracking-wider text-[var(--text-tertiary)]"
                      >
                        SMILES
                      </th>
                      <th
                        scope="col"
                        className="py-1.5 text-right font-semibold uppercase tracking-wider text-[var(--text-tertiary)]"
                      >
                        Tanimoto
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-default)]">
                    {compound.related_compounds.map((relatedCompound) => (
                      <tr key={relatedCompound.cid}>
                        <td className="py-1.5 text-[var(--text-primary)]">
                          {relatedCompound.name ??
                            `PubChem CID ${relatedCompound.cid}`}
                        </td>
                        <td className="max-w-[120px] truncate py-1.5 font-mono text-[var(--text-secondary)]">
                          {truncate(relatedCompound.canonical_smiles, 24)}
                        </td>
                        <td className="py-1.5 text-right">
                          <SimilarityMeter
                            compoundName={
                              relatedCompound.name ??
                              `PubChem CID ${relatedCompound.cid}`
                            }
                            similarity={relatedCompound.tanimoto_similarity}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
