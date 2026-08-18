"use client";

import {
  printBrandFooterText,
  type PrintReportBranding,
} from "./print-report-branding";

interface PrintReportFooterProps {
  branding?: PrintReportBranding;
}

export function PrintReportFooter({ branding }: PrintReportFooterProps) {
  return (
    <div
      className="print-footer"
      style={{
        borderTop: "1px solid #D7ECE5",
        paddingTop: 6,
      }}
    >
      <p style={{ fontSize: "8pt", color: "#0B1F24" }}>
        {printBrandFooterText(branding)}
      </p>
    </div>
  );
}
