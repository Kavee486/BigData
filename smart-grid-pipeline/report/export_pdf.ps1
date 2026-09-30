# Converts report/EC8202_MiniProject_Report.docx to PDF with Microsoft Word,
# refreshing the table of contents first. Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File report/export_pdf.ps1
$docx = Resolve-Path "report/EC8202_MiniProject_Report.docx"
$pdf = [string](Join-Path (Split-Path $docx.Path) "EC8202_MiniProject_Report.pdf")
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($docx.Path, $false, $false)
    foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
    $doc.Fields.Update() | Out-Null
    $doc.Repaginate()
    foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
    $doc.Save()
    $doc.ExportAsFixedFormat([string]$pdf, 17)   # 17 = wdExportFormatPDF
    "pages: " + $doc.ComputeStatistics(2)
    $doc.Close([ref]0)
    "wrote $pdf"
}
finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
