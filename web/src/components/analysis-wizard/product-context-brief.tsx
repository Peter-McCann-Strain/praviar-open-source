"use client";

import {
  CalendarClock,
  ChevronDown,
  ClipboardCheck,
  Landmark,
  MapPinned,
  PackageCheck,
  Pill,
  Plus,
  Route,
  Sparkles,
  Syringe,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  PRODUCT_CONTEXT_LABELS,
  contextListToText,
  getProductContextLaunchGaps,
  getProductContextLaunchRequiredFields,
  getProductContextEntries,
  getProductContextGaps,
  isProductContextLaunchGated,
  parseContextList,
} from "@/lib/product-context";
import { cn } from "@/lib/utils";
import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";
import type {
  AccusedActRecordValue,
  MatterScopePreflightValue,
  ProductContextValue,
} from "@/types/pipeline";

interface ProductContextBriefProps {
  className?: string;
  matterScope: MatterScopePreflightValue;
  onChange: (value: ProductContextValue) => void;
  value: ProductContextValue;
}

interface TextFieldSpec {
  helper: string;
  key: keyof ProductContextValue;
  placeholder: string;
}

interface ListFieldSpec {
  helper: string;
  key: keyof ProductContextValue;
  placeholder: string;
}

const PRODUCT_FIELDS: TextFieldSpec[] = [
  {
    key: "productName",
    placeholder: "PRV-142 oral tablet",
    helper: "Program, brand, or internal product name.",
  },
  {
    key: "dosageForm",
    placeholder: "Film-coated tablet",
    helper: "Tablet, capsule, injection, patch, device/drug kit.",
  },
  {
    key: "routeOfAdministration",
    placeholder: "Oral",
    helper: "Oral, IV, subcutaneous, inhaled, topical.",
  },
  {
    key: "strength",
    placeholder: "25 mg once daily",
    helper: "Dose strength, concentration, or unit dose.",
  },
  {
    key: "releaseProfile",
    placeholder: "Immediate release",
    helper: "Immediate, delayed, extended, depot, controlled.",
  },
  {
    key: "saltPolymorphForm",
    placeholder: "Free base, Form A",
    helper: "Salt, polymorph, hydrate, solvate, crystal form.",
  },
];

const USE_FIELDS: TextFieldSpec[] = [
  {
    key: "indication",
    placeholder: "Moderate-to-severe plaque psoriasis",
    helper: "Therapeutic use or method-of-treatment focus.",
  },
  {
    key: "patientPopulation",
    placeholder: "Adults with prior biologic exposure",
    helper: "Population, line of therapy, biomarkers, exclusions.",
  },
  {
    key: "referenceProduct",
    placeholder: "Reference listed drug or comparator",
    helper: "Comparator, originator, listed drug, or benchmark product.",
  },
  {
    key: "commercialAction",
    placeholder: "US launch diligence before term sheet",
    helper:
      "Reviewer narrative only. Add structured accused acts below for decisioning.",
  },
  {
    key: "decisionDeadline",
    placeholder: "Board packet due 2026-08-15",
    helper: "Internal date or deal milestone driving the review.",
  },
];

const PROCESS_FIELDS: TextFieldSpec[] = [
  {
    key: "manufacturingRoute",
    placeholder: "Final API crystallized from ethanol; no lyophilization",
    helper: "Route, intermediate, purification, device, or CMC fact.",
  },
  {
    key: "ownedOrLicensedIp",
    placeholder: "Owned family PRV-US-17 licensed from AcmeBio",
    helper: "Internal, owned, optioned, or licensed IP position.",
  },
];

const LIST_FIELDS: ListFieldSpec[] = [
  {
    key: "keyExcipients",
    placeholder: "Lactose monohydrate, HPMC, magnesium stearate",
    helper: "Separate excipients with commas.",
  },
  {
    key: "combinationAssets",
    placeholder: "Drug A, device injector, companion diagnostic",
    helper: "Other active ingredients, device parts, kits, diagnostics.",
  },
  {
    key: "commercialTerritories",
    placeholder: "US, EP, UK",
    helper: "Territories that matter commercially.",
  },
  {
    key: "knownPatentsOrAssignees",
    placeholder: "US12345678, Novartis, WO2024...",
    helper: "Known art, competitors, assignees, or licensed families.",
  },
];

const ALL_TEXT_FIELDS = [...PRODUCT_FIELDS, ...USE_FIELDS, ...PROCESS_FIELDS];

function fieldId(key: keyof ProductContextValue) {
  return `product-context-${key}`;
}

function getPriorityContextFieldKeys(
  matterScope: MatterScopePreflightValue,
): Array<keyof ProductContextValue> {
  const keys: Array<keyof ProductContextValue> = ["productName"];
  const actions = new Set(matterScope.intendedActions);

  if (
    matterScope.assetTypeHint === "formulation" ||
    actions.has("formulation_review")
  ) {
    keys.push("dosageForm", "keyExcipients");
  } else if (
    matterScope.assetTypeHint === "process_or_synthesis" ||
    actions.has("manufacture_import")
  ) {
    keys.push("manufacturingRoute", "knownPatentsOrAssignees");
  } else if (actions.has("commercial_launch")) {
    keys.push("commercialAction", "decisionDeadline");
  } else {
    keys.push("indication", "knownPatentsOrAssignees");
  }

  return keys;
}

function ProductTextField({
  field,
  onChange,
  value,
}: {
  field: TextFieldSpec;
  onChange: (key: keyof ProductContextValue, value: string) => void;
  value: ProductContextValue;
}) {
  return (
    <div className="min-w-0 space-y-1.5">
      <Label
        htmlFor={fieldId(field.key)}
        className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]"
      >
        {PRODUCT_CONTEXT_LABELS[field.key]}
      </Label>
      <Input
        id={fieldId(field.key)}
        value={(value[field.key] as string | undefined) ?? ""}
        onChange={(event) => onChange(field.key, event.target.value)}
        placeholder={field.placeholder}
      />
      <p className="text-xs leading-4 text-[var(--text-secondary)]">
        {field.helper}
      </p>
    </div>
  );
}

function ProductListField({
  field,
  onChange,
  value,
}: {
  field: ListFieldSpec;
  onChange: (key: keyof ProductContextValue, value: string[]) => void;
  value: ProductContextValue;
}) {
  const currentValue = Array.isArray(value[field.key])
    ? (value[field.key] as string[])
    : [];

  return (
    <div className="min-w-0 space-y-1.5">
      <Label
        htmlFor={fieldId(field.key)}
        className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]"
      >
        {PRODUCT_CONTEXT_LABELS[field.key]}
      </Label>
      <Textarea
        id={fieldId(field.key)}
        value={contextListToText(currentValue)}
        onChange={(event) =>
          onChange(field.key, parseContextList(event.target.value))
        }
        placeholder={field.placeholder}
        className="min-h-[5.5rem]"
      />
      <p className="text-xs leading-4 text-[var(--text-secondary)]">
        {field.helper}
      </p>
    </div>
  );
}

const SELECT_CLASS_NAME =
  "praviar-glass-field h-10 w-full rounded-lg px-3 text-sm text-[var(--text-primary)] focus:border-brand-primary/60 focus:outline-none focus:ring-2 focus:ring-brand-primary/70";

function BooleanFactSelect({
  label,
  onChange,
  value,
}: {
  label: string;
  onChange: (value: boolean | undefined) => void;
  value: boolean | undefined;
}) {
  return (
    <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
      {label}
      <select
        aria-label={label}
        className={SELECT_CLASS_NAME}
        value={value === undefined ? "unknown" : value ? "yes" : "no"}
        onChange={(event) =>
          onChange(
            event.target.value === "unknown"
              ? undefined
              : event.target.value === "yes",
          )
        }
      >
        <option value="unknown">Not established</option>
        <option value="yes">Yes — verified</option>
        <option value="no">No — verified</option>
      </select>
    </label>
  );
}

function AccusedActsEditor({
  indication,
  onChange,
  productName,
  value,
}: {
  indication?: string;
  onChange: (records: AccusedActRecordValue[]) => void;
  productName?: string;
  value: AccusedActRecordValue[];
}) {
  const updateRecord = (
    index: number,
    patch: Partial<AccusedActRecordValue>,
  ) => {
    onChange(
      value.map((record, recordIndex) =>
        recordIndex === index ? { ...record, ...patch } : record,
      ),
    );
  };

  const addRecord = () => {
    onChange([
      ...value,
      {
        act: "sale",
        jurisdiction: "",
        startDate: "",
        actor: "",
        status: "planned",
        purpose: "commercial",
        regulatoryPath: "none",
        instrumentality: "",
        liabilityTheory: "direct",
      },
    ]);
  };

  return (
    <div className="mt-4 rounded-lg border border-brand-primary/15 bg-[var(--surface-subtle)] p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            Structured accused acts
          </p>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-[var(--text-secondary)]">
            Record the exact act, actor, country, date, status, purpose, and
            product. Denied and hypothetical rows remain context only and cannot
            establish exposure.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={addRecord}
          className="shrink-0"
        >
          <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
          Add act
        </Button>
      </div>

      {value.length === 0 ? (
        <div className="mt-3 rounded-md border border-dashed border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-3 text-xs leading-5 text-[var(--text-secondary)]">
          No governing act supplied. Narrative text and review goals alone
          cannot support an infringement decision.
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          {value.map((record, index) => (
            <fieldset
              key={`${index}-${record.act}-${record.startDate}`}
              className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] p-3"
            >
              <legend className="px-1 text-xs font-semibold text-[var(--text-primary)]">
                Act {index + 1}
              </legend>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                  Act
                  <select
                    aria-label={`Act ${index + 1} type`}
                    className={SELECT_CLASS_NAME}
                    value={record.act}
                    onChange={(event) => {
                      const act = event.target
                        .value as AccusedActRecordValue["act"];
                      updateRecord(index, {
                        act,
                        purpose:
                          act === "regulatory_submission"
                            ? "regulatory_approval"
                            : record.purpose,
                        regulatoryPath:
                          act === "regulatory_submission"
                            ? record.regulatoryPath === "none"
                              ? "anda"
                              : record.regulatoryPath
                            : "none",
                        liabilityTheory:
                          act === "regulatory_submission"
                            ? "artificial_infringement"
                            : record.liabilityTheory ===
                                "artificial_infringement"
                              ? "direct"
                              : record.liabilityTheory,
                        targetProductIdentity:
                          act === "regulatory_submission"
                            ? record.targetProductIdentity ||
                              productName ||
                              undefined
                            : undefined,
                        proposedIndication:
                          act === "regulatory_submission"
                            ? record.proposedIndication ||
                              indication ||
                              undefined
                            : undefined,
                        proposedLabelUse:
                          act === "regulatory_submission"
                            ? record.proposedLabelUse
                            : undefined,
                        labelCarveOutState:
                          act === "regulatory_submission"
                            ? record.labelCarveOutState || "unknown"
                            : undefined,
                        claimedUseMatchReceipts:
                          act === "regulatory_submission"
                            ? record.claimedUseMatchReceipts || []
                            : [],
                      });
                    }}
                  >
                    <option value="manufacture">Manufacture</option>
                    <option value="import">Import</option>
                    <option value="offer_for_sale">Offer for sale</option>
                    <option value="sale">Sale</option>
                    <option value="use">Use</option>
                    <option value="regulatory_submission">
                      Regulatory submission
                    </option>
                  </select>
                </label>
                <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                  Status
                  <select
                    aria-label={`Act ${index + 1} status`}
                    className={SELECT_CLASS_NAME}
                    value={record.status}
                    onChange={(event) =>
                      updateRecord(index, {
                        status: event.target
                          .value as AccusedActRecordValue["status"],
                      })
                    }
                  >
                    <option value="planned">Planned</option>
                    <option value="actual">Actual</option>
                    <option value="denied">Explicitly denied</option>
                    <option value="hypothetical">Hypothetical only</option>
                  </select>
                </label>
                <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                  Jurisdiction
                  <Input
                    aria-label={`Act ${index + 1} jurisdiction`}
                    value={record.jurisdiction}
                    onChange={(event) =>
                      updateRecord(index, {
                        jurisdiction: event.target.value.toUpperCase(),
                      })
                    }
                    placeholder="US"
                    maxLength={40}
                  />
                </label>
                <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                  Start date
                  <Input
                    aria-label={`Act ${index + 1} start date`}
                    type="date"
                    value={record.startDate}
                    onChange={(event) =>
                      updateRecord(index, { startDate: event.target.value })
                    }
                  />
                </label>
                <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                  End date (if bounded)
                  <Input
                    aria-label={`Act ${index + 1} end date`}
                    type="date"
                    value={record.endDate ?? ""}
                    min={record.startDate || undefined}
                    onChange={(event) =>
                      updateRecord(index, {
                        endDate: event.target.value || undefined,
                      })
                    }
                  />
                </label>
                <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                  Actor
                  <Input
                    aria-label={`Act ${index + 1} actor`}
                    value={record.actor}
                    onChange={(event) =>
                      updateRecord(index, { actor: event.target.value })
                    }
                    placeholder="Applicant or operating entity"
                    maxLength={240}
                  />
                </label>
                <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                  Purpose
                  <select
                    aria-label={`Act ${index + 1} purpose`}
                    className={SELECT_CLASS_NAME}
                    value={record.purpose}
                    disabled={record.act === "regulatory_submission"}
                    onChange={(event) =>
                      updateRecord(index, {
                        purpose: event.target
                          .value as AccusedActRecordValue["purpose"],
                      })
                    }
                  >
                    <option value="commercial">Commercial</option>
                    <option value="regulatory_approval">
                      Regulatory approval
                    </option>
                    <option value="clinical_research">Clinical research</option>
                    <option value="experimental">Experimental</option>
                    <option value="internal_research">Internal research</option>
                    <option value="other">Other</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </label>
                {record.act === "regulatory_submission" ? (
                  <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                    Regulatory path
                    <select
                      aria-label={`Act ${index + 1} regulatory path`}
                      className={SELECT_CLASS_NAME}
                      value={record.regulatoryPath}
                      onChange={(event) =>
                        updateRecord(index, {
                          regulatoryPath: event.target
                            .value as AccusedActRecordValue["regulatoryPath"],
                        })
                      }
                    >
                      <option value="anda">ANDA</option>
                      <option value="nda_505_b_2">505(b)(2) NDA</option>
                      <option value="nda_505_b_1">505(b)(1) NDA</option>
                      <option value="biosimilar_351_k">
                        351(k) biosimilar application
                      </option>
                      <option value="abla">aBLA</option>
                      <option value="bla_351_a">351(a) BLA</option>
                      <option value="unknown">Unknown</option>
                    </select>
                  </label>
                ) : null}
                <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                  Liability theory
                  <select
                    aria-label={`Act ${index + 1} liability theory`}
                    className={SELECT_CLASS_NAME}
                    value={record.liabilityTheory}
                    disabled={record.act === "regulatory_submission"}
                    onChange={(event) =>
                      updateRecord(index, {
                        liabilityTheory: event.target
                          .value as AccusedActRecordValue["liabilityTheory"],
                      })
                    }
                  >
                    <option value="direct">Direct practice</option>
                    <option value="induced">Induced infringement</option>
                    <option value="contributory">
                      Contributory infringement
                    </option>
                    <option value="unknown">Unresolved</option>
                    {record.act === "regulatory_submission" ? (
                      <option value="artificial_infringement">
                        Statutory submission
                      </option>
                    ) : null}
                  </select>
                </label>
                <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)] md:col-span-2">
                  Product or instrumentality
                  <Input
                    aria-label={`Act ${index + 1} instrumentality`}
                    value={record.instrumentality}
                    onChange={(event) =>
                      updateRecord(index, {
                        instrumentality: event.target.value,
                      })
                    }
                    placeholder="Exact candidate, formulation, process, or proposed label"
                    maxLength={500}
                  />
                </label>
              </div>
              {record.act === "regulatory_submission" ? (
                <div className="mt-3 grid gap-3 rounded-md border border-brand-primary/15 bg-brand-primary/5 p-3 md:grid-cols-2">
                  <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                    Exact submitted product identity
                    <Input
                      aria-label={`Act ${index + 1} target product identity`}
                      value={record.targetProductIdentity ?? ""}
                      onChange={(event) =>
                        updateRecord(index, {
                          targetProductIdentity:
                            event.target.value || undefined,
                        })
                      }
                      placeholder="Must match the resolved compound or biologic"
                    />
                  </label>
                  <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                    Proposed indication
                    <Input
                      aria-label={`Act ${index + 1} proposed indication`}
                      value={record.proposedIndication ?? ""}
                      onChange={(event) =>
                        updateRecord(index, {
                          proposedIndication: event.target.value || undefined,
                        })
                      }
                      placeholder="Exact proposed indication"
                    />
                  </label>
                  <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)] md:col-span-2">
                    Proposed label use
                    <Textarea
                      aria-label={`Act ${index + 1} proposed label use`}
                      value={record.proposedLabelUse ?? ""}
                      onChange={(event) =>
                        updateRecord(index, {
                          proposedLabelUse: event.target.value || undefined,
                        })
                      }
                      placeholder="Exact indication, population, dose, route, and administration language"
                      className="min-h-[5.5rem]"
                    />
                  </label>
                  <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                    Skinny-label carve-out
                    <select
                      aria-label={`Act ${index + 1} label carve-out state`}
                      className={SELECT_CLASS_NAME}
                      value={record.labelCarveOutState ?? "unknown"}
                      onChange={(event) =>
                        updateRecord(index, {
                          labelCarveOutState: event.target.value as NonNullable<
                            AccusedActRecordValue["labelCarveOutState"]
                          >,
                        })
                      }
                    >
                      <option value="unknown">Not assessed</option>
                      <option value="none">No carve-out</option>
                      <option value="partial">Partial carve-out</option>
                      <option value="complete">Complete carve-out</option>
                    </select>
                  </label>
                  <div
                    className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]"
                    role="status"
                  >
                    <span className="font-semibold text-[var(--text-primary)]">
                      Claimed-use verification:
                    </span>{" "}
                    {record.claimedUseMatchReceipts?.length
                      ? `${record.claimedUseMatchReceipts.length} server-attested receipt(s) attached.`
                      : "Not attached. The submission cannot establish a method-of-use claim match."}
                  </div>
                </div>
              ) : null}
              {record.liabilityTheory === "direct" &&
              (record.act === "use" || record.act === "manufacture") ? (
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <BooleanFactSelect
                    label={`Act ${index + 1} actor performs every claimed step`}
                    value={record.performsAllClaimSteps}
                    onChange={(fact) =>
                      updateRecord(index, {
                        performsAllClaimSteps: fact,
                      })
                    }
                  />
                </div>
              ) : null}
              {record.liabilityTheory === "induced" ? (
                <div className="mt-3 grid gap-3 rounded-md border border-warning/20 bg-warning/5 p-3 md:grid-cols-2 xl:grid-cols-4">
                  <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                    Identified direct infringer
                    <Input
                      aria-label={`Act ${index + 1} direct infringer`}
                      value={record.directInfringer ?? ""}
                      onChange={(event) =>
                        updateRecord(index, {
                          directInfringer: event.target.value || undefined,
                        })
                      }
                      placeholder="Prescriber, patient, or customer"
                    />
                  </label>
                  <BooleanFactSelect
                    label={`Act ${index + 1} direct infringer performs every claimed step`}
                    value={record.performsAllClaimSteps}
                    onChange={(fact) =>
                      updateRecord(index, {
                        performsAllClaimSteps: fact,
                      })
                    }
                  />
                  <BooleanFactSelect
                    label={`Act ${index + 1} accused actor knew of the patent`}
                    value={record.knowledgeOfPatent}
                    onChange={(fact) =>
                      updateRecord(index, { knowledgeOfPatent: fact })
                    }
                  />
                  <BooleanFactSelect
                    label={`Act ${index + 1} affirmative encouragement verified`}
                    value={record.affirmativeEncouragement}
                    onChange={(fact) =>
                      updateRecord(index, {
                        affirmativeEncouragement: fact,
                      })
                    }
                  />
                </div>
              ) : null}
              {record.liabilityTheory === "direct" &&
              ["import", "offer_for_sale", "sale", "use"].includes(
                record.act,
              ) ? (
                <details className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-3">
                  <summary className="cursor-pointer text-xs font-semibold text-[var(--text-primary)]">
                    Foreign-process linkage (§271(g))
                  </summary>
                  <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)]">
                      Manufacturing jurisdiction
                      <Input
                        aria-label={`Act ${index + 1} manufacturing jurisdiction`}
                        value={record.manufacturingJurisdiction ?? ""}
                        onChange={(event) =>
                          updateRecord(index, {
                            manufacturingJurisdiction:
                              event.target.value.toUpperCase() || undefined,
                          })
                        }
                        placeholder="CN"
                      />
                    </label>
                    <label className="space-y-1 text-xs font-medium text-[var(--text-secondary)] md:col-span-2">
                      Process used abroad
                      <Input
                        aria-label={`Act ${index + 1} process used`}
                        value={record.processUsed ?? ""}
                        onChange={(event) =>
                          updateRecord(index, {
                            processUsed: event.target.value || undefined,
                          })
                        }
                        placeholder="Verified process facts tied to the imported product"
                      />
                    </label>
                    <BooleanFactSelect
                      label={`Act ${index + 1} foreign process use verified`}
                      value={record.processUseVerified}
                      onChange={(fact) =>
                        updateRecord(index, { processUseVerified: fact })
                      }
                    />
                    <BooleanFactSelect
                      label={`Act ${index + 1} product materially changed after process`}
                      value={record.materiallyChangedAfterProcess}
                      onChange={(fact) =>
                        updateRecord(index, {
                          materiallyChangedAfterProcess: fact,
                        })
                      }
                    />
                    <BooleanFactSelect
                      label={`Act ${index + 1} product is only a trivial component`}
                      value={record.trivialComponentAfterProcess}
                      onChange={(fact) =>
                        updateRecord(index, {
                          trivialComponentAfterProcess: fact,
                        })
                      }
                    />
                  </div>
                </details>
              ) : null}
              <div className="mt-3 flex justify-end">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    onChange(
                      value.filter(
                        (_record, recordIndex) => recordIndex !== index,
                      ),
                    )
                  }
                  className="text-error hover:text-error"
                  aria-label={`Remove act ${index + 1}`}
                >
                  <Trash2 className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                  Remove
                </Button>
              </div>
            </fieldset>
          ))}
        </div>
      )}
    </div>
  );
}

export function ProductContextBrief({
  className,
  matterScope,
  onChange,
  value,
}: ProductContextBriefProps) {
  const capturedEntries = getProductContextEntries(value);
  const gaps = getProductContextGaps({ context: value, matterScope });
  const launchGaps = getProductContextLaunchGaps({
    context: value,
    matterScope,
  });
  const launchGapLabels = launchGaps.map(
    (field) => PRODUCT_CONTEXT_LABELS[field],
  );
  const gapLabels = gaps.map((field) => PRODUCT_CONTEXT_LABELS[field]);
  const completenessTone = gaps.length === 0 ? "ready" : "attention";
  const launchGated = isProductContextLaunchGated(matterScope);
  const priorityFieldKeys = new Set([
    ...getPriorityContextFieldKeys(matterScope),
    ...getProductContextLaunchRequiredFields(matterScope),
  ]);
  const priorityTextFields = ALL_TEXT_FIELDS.filter((field) =>
    priorityFieldKeys.has(field.key),
  );
  const priorityListFields = LIST_FIELDS.filter((field) =>
    priorityFieldKeys.has(field.key),
  );
  const additionalTextFields = ALL_TEXT_FIELDS.filter(
    (field) => !priorityFieldKeys.has(field.key),
  );
  const additionalListFields = LIST_FIELDS.filter(
    (field) => !priorityFieldKeys.has(field.key),
  );

  const setTextField = (key: keyof ProductContextValue, fieldValue: string) => {
    onChange({ ...value, [key]: fieldValue });
  };
  const setListField = (
    key: keyof ProductContextValue,
    fieldValue: string[],
  ) => {
    onChange({ ...value, [key]: fieldValue });
  };

  return (
    <ResponsiveDisclosure
      className="group min-w-0 sm:block"
      data-testid="product-context-mobile-disclosure"
      summary={
        <summary className="flex min-h-16 cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-brand-primary/15 bg-[var(--surface-card)] px-3 py-3 text-left shadow-[var(--shadow-xs)] marker:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:hidden [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Product context
            </span>
            <span className="mt-0.5 block text-sm font-semibold text-[var(--text-primary)]">
              {capturedEntries.length} captured · {gapLabels.length} open
            </span>
            <span className="mt-0.5 line-clamp-1 block text-xs text-[var(--text-secondary)]">
              Add formulation, use, process, territory, and known-art facts.
            </span>
          </span>
          <ChevronDown
            className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180 motion-reduce:transition-none"
            aria-hidden="true"
          />
        </summary>
      }
    >
      <section
        aria-label="Product context intake"
        className={cn(
          "mt-2 overflow-hidden rounded-lg border border-brand-primary/15 bg-[var(--surface-card)] shadow-[var(--shadow-sm)] sm:mt-0",
          className,
        )}
      >
        <div className="border-b border-[var(--border-subtle)] bg-[var(--surface-glass)] p-3 sm:p-5">
          <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Product context
              </p>
              <h2 className="mt-1 flex items-center gap-2 text-base font-semibold text-[var(--text-primary)]">
                <PackageCheck
                  className="h-4 w-4 text-brand-primary"
                  aria-hidden="true"
                />
                Product facts that change FTO
              </h2>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
                Capture formulation, use, process, territory, and known-art
                facts before launch. Leave unknowns blank for early diligence
                screens; enter values or &quot;Unknown&quot; for commercial
                launch and manufacture/import matters.
              </p>
            </div>
            <div
              className={cn(
                "rounded-md border px-3 py-2 text-xs",
                completenessTone === "ready"
                  ? "border-success/25 bg-success/10 text-success"
                  : "border-warning/30 bg-warning/10 text-warning",
              )}
            >
              <p className="font-semibold">
                {capturedEntries.length.toLocaleString()} fact
                {capturedEntries.length === 1 ? "" : "s"} captured
              </p>
              <p className="mt-1 text-xs leading-4 text-[var(--text-secondary)]">
                {gapLabels.length === 0
                  ? "Core review facts are present for this matter type."
                  : `Open gaps: ${gapLabels.slice(0, 4).join(", ")}${
                      gapLabels.length > 4 ? "..." : ""
                    }`}
              </p>
            </div>
          </div>
        </div>

        <div className="grid gap-4 p-3 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,0.34fr)] sm:p-5">
          <div className="min-w-0 space-y-5">
            <div>
              <div className="mb-3 flex min-w-0 items-start gap-2 rounded-md border border-brand-primary/15 bg-brand-primary/8 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                <Sparkles
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-primary"
                  aria-hidden="true"
                />
                <p>
                  Praviar is prioritizing the context fields most likely to move
                  this matter. Additional product facts remain available below.
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {priorityTextFields.map((field) => (
                  <ProductTextField
                    key={field.key}
                    field={field}
                    value={value}
                    onChange={setTextField}
                  />
                ))}
                {priorityListFields.map((field) => (
                  <ProductListField
                    key={field.key}
                    field={field}
                    value={value}
                    onChange={setListField}
                  />
                ))}
              </div>
              <AccusedActsEditor
                productName={value.productName}
                indication={value.indication}
                value={value.accusedActs ?? []}
                onChange={(records) =>
                  onChange({ ...value, accusedActs: records })
                }
              />
            </div>

            <details className="group rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)]">
              <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/60 [&::-webkit-details-marker]:hidden">
                <span className="min-w-0">
                  <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    Additional product facts
                  </span>
                  <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                    Formulation, use, process, territory, and known-art details
                    for deeper reviewer context.
                  </span>
                </span>
                <ChevronDown
                  className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180"
                  aria-hidden="true"
                />
              </summary>
              <div className="space-y-5 border-t border-[var(--border-subtle)] p-3">
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {additionalTextFields.map((field) => (
                    <ProductTextField
                      key={field.key}
                      field={field}
                      value={value}
                      onChange={setTextField}
                    />
                  ))}
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  {additionalListFields.map((field) => (
                    <ProductListField
                      key={field.key}
                      field={field}
                      value={value}
                      onChange={setListField}
                    />
                  ))}
                </div>
              </div>
            </details>
          </div>

          <div
            className="space-y-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-3"
            role="note"
            aria-label="Reviewer-ready product context brief"
          >
            <div className="flex items-start gap-2">
              <span
                className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-brand-primary/20 bg-brand-primary/10 text-brand-primary"
                aria-hidden="true"
              >
                <Sparkles className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  Reviewer-ready brief
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  Praviar carries these facts into the launch contract for
                  evidence routing and reviewer handoff.
                </p>
              </div>
            </div>

            <div className="grid gap-2 text-xs">
              {[
                {
                  icon: Pill,
                  label: "Product",
                  value: value.dosageForm || "Form pending",
                },
                {
                  icon: Route,
                  label: "Route",
                  value: value.routeOfAdministration || "Route pending",
                },
                {
                  icon: Syringe,
                  label: "Use",
                  value: value.indication || "Use pending",
                },
                {
                  icon: PackageCheck,
                  label: "Process",
                  value: value.manufacturingRoute || "Process pending",
                },
                {
                  icon: MapPinned,
                  label: "Territory",
                  value:
                    value.commercialTerritories &&
                    value.commercialTerritories.length > 0
                      ? value.commercialTerritories.join(", ")
                      : "Territory required for exposure",
                },
                {
                  icon: Landmark,
                  label: "Known art",
                  value:
                    value.knownPatentsOrAssignees &&
                    value.knownPatentsOrAssignees.length > 0
                      ? value.knownPatentsOrAssignees.join(", ")
                      : "None supplied",
                },
                {
                  icon: CalendarClock,
                  label: "Deadline",
                  value: value.decisionDeadline || "No deadline supplied",
                },
                {
                  icon: ClipboardCheck,
                  label: "Captured",
                  value: `${capturedEntries.length} context field${
                    capturedEntries.length === 1 ? "" : "s"
                  }`,
                },
              ].map((item) => {
                const Icon = item.icon;
                return (
                  <div
                    key={item.label}
                    className="grid min-w-0 grid-cols-[1.75rem_minmax(0,1fr)] gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] px-2.5 py-2"
                  >
                    <Icon
                      className="mt-0.5 h-4 w-4 text-brand-primary"
                      aria-hidden="true"
                    />
                    <span className="min-w-0">
                      <span className="block text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
                        {item.label}
                      </span>
                      <span className="mt-0.5 block text-xs font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]">
                        {item.value}
                      </span>
                    </span>
                  </div>
                );
              })}
            </div>

            {launchGapLabels.length > 0 ? (
              <div className="rounded-md border border-error/25 bg-error/10 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                <span className="font-semibold text-error">
                  Launch blocked:
                </span>{" "}
                {launchGapLabels.join(", ")}. Enter facts or &quot;Unknown&quot;
                before submission.
              </div>
            ) : gapLabels.length > 0 ? (
              <div className="rounded-md border border-warning/25 bg-warning/10 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                <span className="font-semibold text-warning">
                  Open context:
                </span>{" "}
                {gapLabels.join(", ")}.{" "}
                {launchGated
                  ? "Core launch fields are explicit; remaining context can follow in review."
                  : "Launch remains available when unknown."}
              </div>
            ) : (
              <div className="rounded-md border border-success/25 bg-success/10 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                <span className="font-semibold text-success">
                  Core context ready.
                </span>{" "}
                Reviewers can see the product, use, and action assumptions.
              </div>
            )}
          </div>
        </div>
      </section>
    </ResponsiveDisclosure>
  );
}
