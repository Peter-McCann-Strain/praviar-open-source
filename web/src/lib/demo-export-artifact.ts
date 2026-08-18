export const DEMO_EXPORT_FORMATS = [
  "pdf",
  "docx",
  "pptx",
  "csv",
  "xlsx",
  "json",
] as const;

export const DEMO_EXPORT_AUDIENCES = [
  "full",
  "executive",
  "attorney",
  "scientist",
  "investor",
] as const;

export type DemoExportFormat = (typeof DEMO_EXPORT_FORMATS)[number];
export type DemoExportAudience = (typeof DEMO_EXPORT_AUDIENCES)[number];

export interface DemoExportDescriptor {
  audience: DemoExportAudience;
  format: DemoExportFormat;
}

export interface DemoExportArtifact {
  bytes: Uint8Array;
  fileName: string;
  mediaType: string;
}

const DESCRIPTOR_PATTERN =
  /^praviar-demo-export:v1:(full|executive|attorney|scientist|investor):(pdf|docx|pptx|csv|xlsx|json)$/u;
const textEncoder = new TextEncoder();

const AUDIENCE_LABELS: Record<DemoExportAudience, string> = {
  attorney: "Patent Counsel",
  executive: "Executive Brief",
  full: "Full Report",
  investor: "Investor Pack",
  scientist: "R&D Brief",
};

const DEMO_FINDINGS = [
  ["Overall posture", "Review required; no legal conclusion represented"],
  [
    "Material patent families",
    `${SHOWCASE_PAYLOAD.analysis.families.length} synthetic examples`,
  ],
  [
    "Claim-chart coverage",
    `${SHOWCASE_PAYLOAD.analysis.families.reduce((count, family) => count + family.claims.length, 0)} synthetic claims mapped`,
  ],
  [
    "Source health",
    `${SHOWCASE_PAYLOAD.analysis.searched_sources.length} synthetic sources disclosed`,
  ],
] as const;

export function buildDemoExportDescriptor(
  audience: DemoExportAudience,
  format: DemoExportFormat,
): string {
  return `praviar-demo-export:v1:${audience}:${format}`;
}

export function parseDemoExportDescriptor(
  value: string,
): DemoExportDescriptor | null {
  if (!value || value !== value.trim()) return null;
  const match = DESCRIPTOR_PATTERN.exec(value);
  if (!match) return null;
  return {
    audience: match[1] as DemoExportAudience,
    format: match[2] as DemoExportFormat,
  };
}

export function createDemoExportArtifact(
  audience: DemoExportAudience,
  format: DemoExportFormat,
): DemoExportArtifact {
  const label = AUDIENCE_LABELS[audience];
  const baseName = `praviar-demo-${audience}`;

  switch (format) {
    case "pdf":
      return {
        bytes: buildPdf(label),
        fileName: `${baseName}.pdf`,
        mediaType: "application/pdf",
      };
    case "docx":
      return {
        bytes: buildDocx(label),
        fileName: `${baseName}.docx`,
        mediaType:
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      };
    case "pptx":
      return {
        bytes: buildPptx(label),
        fileName: `${baseName}.pptx`,
        mediaType:
          "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      };
    case "csv":
      return {
        bytes: textEncoder.encode(buildCsv(label)),
        fileName: `${baseName}.csv`,
        mediaType: "text/csv;charset=utf-8",
      };
    case "xlsx":
      return {
        bytes: buildXlsx(label),
        fileName: `${baseName}.xlsx`,
        mediaType:
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      };
    case "json":
      return {
        bytes: textEncoder.encode(buildJson(label)),
        fileName: `${baseName}.json`,
        mediaType: "application/json",
      };
  }
}

export function createDemoReportPayload(
  audience: DemoExportAudience,
): Uint8Array {
  return textEncoder.encode(
    JSON.stringify({
      audience,
      disclaimer:
        "Synthetic demonstration data only. This is not a legal opinion or clearance decision.",
      findings: Object.fromEntries(DEMO_FINDINGS),
      report_id: "praviar-synthetic-demo-v1",
      schema_version: "demo-report-v1",
    }),
  );
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error("Secure hashing is unavailable in this browser");
  }
  const digest = await globalThis.crypto.subtle.digest(
    "SHA-256",
    bytes.slice().buffer,
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

function buildJson(label: string): string {
  return `${JSON.stringify(
    {
      artifact: `${label} demonstration export`,
      disclaimer:
        "Synthetic demonstration data only. Counsel review is required before reliance.",
      findings: DEMO_FINDINGS.map(([category, finding]) => ({
        category,
        finding,
      })),
      generated_by: "Praviar demonstration workspace",
      report_id: "praviar-synthetic-demo-v1",
    },
    null,
    2,
  )}\n`;
}

function buildCsv(label: string): string {
  const rows = [
    ["Praviar demonstration export", label],
    [
      "Disclaimer",
      "Synthetic demonstration data only; counsel review is required before reliance.",
    ],
    ["Category", "Finding"],
    ...DEMO_FINDINGS,
  ];
  return `\uFEFF${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`;
}

function csvCell(value: string): string {
  return `"${value.replaceAll('"', '""')}"`;
}

function buildPdf(label: string): Uint8Array {
  const lines = [
    "Praviar demonstration export",
    label,
    "Synthetic demonstration data only.",
    "Counsel review is required before reliance.",
    ...DEMO_FINDINGS.map(([category, finding]) => `${category}: ${finding}`),
  ];
  const stream = lines
    .map(
      (line, index) =>
        `BT ${index === 0 ? "/F1 16 Tf" : "/F1 10 Tf"} 1 0 0 1 72 ${742 - index * 28} Tm (${pdfText(line)}) Tj ET`,
    )
    .join("\n")
    .concat("\n");
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${textEncoder.encode(stream).length} >>\nstream\n${stream}endstream`,
  ];
  const chunks: string[] = ["%PDF-1.7\n%Praviar\n"];
  const offsets: number[] = [0];
  let byteLength = textEncoder.encode(chunks[0]).length;
  objects.forEach((object, index) => {
    offsets.push(byteLength);
    const chunk = `${index + 1} 0 obj\n${object}\nendobj\n`;
    chunks.push(chunk);
    byteLength += textEncoder.encode(chunk).length;
  });
  const xrefOffset = byteLength;
  const xref = [
    "xref",
    `0 ${objects.length + 1}`,
    "0000000000 65535 f ",
    ...offsets
      .slice(1)
      .map((offset) => `${String(offset).padStart(10, "0")} 00000 n `),
    "trailer",
    `<< /Size ${objects.length + 1} /Root 1 0 R >>`,
    "startxref",
    String(xrefOffset),
    "%%EOF",
    "",
  ].join("\n");
  return textEncoder.encode(chunks.join("") + xref);
}

function pdfText(value: string): string {
  return value
    .replaceAll("\\", "\\\\")
    .replaceAll("(", "\\(")
    .replaceAll(")", "\\)")
    .replaceAll("&", "and");
}

function buildDocx(label: string): Uint8Array {
  const paragraphs = [
    "Praviar demonstration export",
    label,
    "Synthetic demonstration data only. Counsel review is required before reliance.",
    ...DEMO_FINDINGS.map(([category, finding]) => `${category}: ${finding}`),
  ];
  return createStoredZip([
    {
      name: "[Content_Types].xml",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
        </Types>`),
    },
    {
      name: "_rels/.rels",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
        </Relationships>`),
    },
    {
      name: "word/document.xml",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            ${paragraphs
              .map(
                (paragraph, index) =>
                  `<w:p><w:r>${index === 0 ? '<w:rPr><w:b/><w:sz w:val="32"/></w:rPr>' : ""}<w:t>${escapeXml(paragraph)}</w:t></w:r></w:p>`,
              )
              .join("")}
            <w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
          </w:body>
        </w:document>`),
    },
  ]);
}

function buildXlsx(label: string): Uint8Array {
  const rows = [
    ["Praviar demonstration export", label],
    [
      "Disclaimer",
      "Synthetic demonstration data only; counsel review is required before reliance.",
    ],
    ["Category", "Finding"],
    ...DEMO_FINDINGS,
  ];
  const sheetRows = rows
    .map(
      (row, rowIndex) =>
        `<row r="${rowIndex + 1}">${row
          .map(
            (value, columnIndex) =>
              `<c r="${String.fromCharCode(65 + columnIndex)}${rowIndex + 1}" t="inlineStr"><is><t>${escapeXml(value)}</t></is></c>`,
          )
          .join("")}</row>`,
    )
    .join("");
  return createStoredZip([
    {
      name: "[Content_Types].xml",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
          <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
        </Types>`),
    },
    {
      name: "_rels/.rels",
      content: packageRelationship("xl/workbook.xml"),
    },
    {
      name: "xl/workbook.xml",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Demonstration" sheetId="1" r:id="rId1"/></sheets>
        </workbook>`),
    },
    {
      name: "xl/_rels/workbook.xml.rels",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
        </Relationships>`),
    },
    {
      name: "xl/worksheets/sheet1.xml",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <sheetData>${sheetRows}</sheetData>
        </worksheet>`),
    },
  ]);
}

function buildPptx(label: string): Uint8Array {
  return createStoredZip([
    {
      name: "[Content_Types].xml",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
          <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
          <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
          <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
          <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
        </Types>`),
    },
    {
      name: "_rels/.rels",
      content: packageRelationship("ppt/presentation.xml"),
    },
    {
      name: "ppt/presentation.xml",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
          <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
          <p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>
          <p:sldSz cx="12192000" cy="6858000" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/>
        </p:presentation>`),
    },
    {
      name: "ppt/_rels/presentation.xml.rels",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
          <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
        </Relationships>`),
    },
    {
      name: "ppt/slides/slide1.xml",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
          <p:cSld><p:spTree>
            <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>
            <p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="914400" y="685800"/><a:ext cx="10363200" cy="1371600"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US" sz="2800" b="1"/><a:t>Praviar demonstration export</a:t></a:r></a:p><a:p><a:r><a:rPr lang="en-US" sz="1800"/><a:t>${escapeXml(label)}</a:t></a:r></a:p></p:txBody></p:sp>
            <p:sp><p:nvSpPr><p:cNvPr id="3" name="Disclaimer"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="914400" y="2743200"/><a:ext cx="10363200" cy="2057400"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US" sz="1600"/><a:t>Synthetic demonstration data only. Counsel review is required before reliance.</a:t></a:r></a:p><a:p><a:r><a:rPr lang="en-US" sz="1400"/><a:t>Overall posture: Moderate; three synthetic patent families shown.</a:t></a:r></a:p></p:txBody></p:sp>
          </p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
        </p:sld>`),
    },
    {
      name: "ppt/slides/_rels/slide1.xml.rels",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
        </Relationships>`),
    },
    {
      name: "ppt/slideLayouts/slideLayout1.xml",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank">
          <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
        </p:sldLayout>`),
    },
    {
      name: "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
        </Relationships>`),
    },
    {
      name: "ppt/slideMasters/slideMaster1.xml",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
          <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
          <p:clrMap accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" bg1="lt1" bg2="lt2" folHlink="folHlink" hlink="hlink" tx1="dk1" tx2="dk2"/>
          <p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
        </p:sldMaster>`),
    },
    {
      name: "ppt/slideMasters/_rels/slideMaster1.xml.rels",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
          <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
        </Relationships>`),
    },
    {
      name: "ppt/theme/theme1.xml",
      content: xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Praviar Demo"><a:themeElements>
          <a:clrScheme name="Praviar"><a:dk1><a:srgbClr val="0B1F24"/></a:dk1><a:lt1><a:srgbClr val="F6F4EF"/></a:lt1><a:dk2><a:srgbClr val="0E6F68"/></a:dk2><a:lt2><a:srgbClr val="D7ECE5"/></a:lt2><a:accent1><a:srgbClr val="0E6F68"/></a:accent1><a:accent2><a:srgbClr val="B87333"/></a:accent2><a:accent3><a:srgbClr val="5FB7A6"/></a:accent3><a:accent4><a:srgbClr val="3C7A89"/></a:accent4><a:accent5><a:srgbClr val="866A3A"/></a:accent5><a:accent6><a:srgbClr val="607D8B"/></a:accent6><a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>
          <a:fontScheme name="Aptos"><a:majorFont><a:latin typeface="Aptos Display"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>
          <a:fmtScheme name="Praviar"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="lt1"/></a:solidFill><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="lt1"/></a:solidFill><a:solidFill><a:schemeClr val="lt2"/></a:solidFill><a:solidFill><a:schemeClr val="dk1"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme>
        </a:themeElements></a:theme>`),
    },
  ]);
}

function packageRelationship(target: string): string {
  return xml(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="${target}"/>
    </Relationships>`);
}

function xml(value: string): string {
  return value.replace(/>\s+</gu, "><").trim();
}

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

interface ZipEntry {
  name: string;
  content: string | Uint8Array;
}

function createStoredZip(entries: ZipEntry[]): Uint8Array {
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let localOffset = 0;

  for (const entry of entries) {
    const name = textEncoder.encode(entry.name);
    const content =
      typeof entry.content === "string"
        ? textEncoder.encode(entry.content)
        : entry.content;
    const crc = crc32(content);
    const localHeader = new Uint8Array(30 + name.length);
    const localView = new DataView(localHeader.buffer);
    writeZipHeader(localView, 0x04034b50, crc, content.length, name.length);
    localHeader.set(name, 30);
    localParts.push(localHeader, content);

    const centralHeader = new Uint8Array(46 + name.length);
    const centralView = new DataView(centralHeader.buffer);
    centralView.setUint32(0, 0x02014b50, true);
    centralView.setUint16(4, 20, true);
    centralView.setUint16(6, 20, true);
    centralView.setUint16(8, 0x0800, true);
    centralView.setUint16(10, 0, true);
    centralView.setUint16(12, 0, true);
    centralView.setUint16(14, 0, true);
    centralView.setUint32(16, crc, true);
    centralView.setUint32(20, content.length, true);
    centralView.setUint32(24, content.length, true);
    centralView.setUint16(28, name.length, true);
    centralView.setUint16(30, 0, true);
    centralView.setUint16(32, 0, true);
    centralView.setUint16(34, 0, true);
    centralView.setUint16(36, 0, true);
    centralView.setUint32(38, 0, true);
    centralView.setUint32(42, localOffset, true);
    centralHeader.set(name, 46);
    centralParts.push(centralHeader);

    localOffset += localHeader.length + content.length;
  }

  const centralDirectory = concatBytes(centralParts);
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(4, 0, true);
  endView.setUint16(6, 0, true);
  endView.setUint16(8, entries.length, true);
  endView.setUint16(10, entries.length, true);
  endView.setUint32(12, centralDirectory.length, true);
  endView.setUint32(16, localOffset, true);
  endView.setUint16(20, 0, true);
  return concatBytes([...localParts, centralDirectory, end]);
}

function writeZipHeader(
  view: DataView,
  signature: number,
  crc: number,
  size: number,
  nameLength: number,
): void {
  view.setUint32(0, signature, true);
  view.setUint16(4, 20, true);
  view.setUint16(6, 0x0800, true);
  view.setUint16(8, 0, true);
  view.setUint16(10, 0, true);
  view.setUint16(12, 0, true);
  view.setUint32(14, crc, true);
  view.setUint32(18, size, true);
  view.setUint32(22, size, true);
  view.setUint16(26, nameLength, true);
  view.setUint16(28, 0, true);
}

function concatBytes(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}
import { SHOWCASE_PAYLOAD } from "@/lib/showcase-report";
