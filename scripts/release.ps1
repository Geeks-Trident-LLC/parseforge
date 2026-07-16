param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "bump-patch",
        "bump-minor",
        "bump-major"
    )]
    $Command
)

function Update-Version([string]$part) {
    bump2version $part
}

switch ($Command) {
    "bump-patch" { Update-Version "patch" }
    "bump-minor" { Update-Version "minor" }
    "bump-major" { Update-Version "major" }
}
