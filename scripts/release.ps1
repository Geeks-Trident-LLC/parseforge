param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "bump-patch",
        "bump-minor",
        "bump-major",
        "release-test",
        "release-prod"
    )]
    $Command
)

function Get-Version {
    @"
import tomllib
print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])
"@ | python
}

function Update-Version([string]$part) {
    bump2version $part
}

function Publish-Test {
    $version = Get-Version
    $tag = "v$version-test"

    Write-Host "Creating TestPyPI tag $tag"

    git rev-parse $tag 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Error "Tag $tag already exists"
        exit 1
    }

    git tag $tag
    git push origin $tag

    Write-Host "TestPyPI tag pushed: $tag"
}

function Publish-Prod {
    $branch = git rev-parse --abbrev-ref HEAD
    if ($branch -ne "main") {
        Write-Error "Must be on main to release to PyPI"
        exit 1
    }

    $version = Get-Version
    $tag = "v$version"

    # Check local tag
    $localTagExists = git tag --list $tag

    # Check remote tag
    $remoteTagExists = git ls-remote --tags origin $tag

    if ($localTagExists -and $remoteTagExists) {
        Write-Error "Tag $tag exists locally AND remotely. Release already completed or inconsistent. Aborting."
        exit 1
    }

    if ($localTagExists -and -not $remoteTagExists) {
        Write-Host "Local tag $tag exists but remote tag does not. Deleting local tag and continuing..."
        git tag -d $tag | Out-Null
        $localTagExists = $null
    }

    if (-not $localTagExists) {
        Write-Host "Creating production tag $tag"
        git tag $tag
    }

    if ($remoteTagExists) {
        Write-Host "Remote tag $tag already exists. Skipping push."
    } else {
        Write-Host "Pushing tag $tag"
        git push origin $tag
    }

    gh release view $tag *>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "GitHub Release $tag already exists. Updating notes."
        gh release edit $tag --generate-notes
    } else {
        Write-Host "Creating GitHub Release for $tag"
        gh release create $tag --generate-notes
    }
}

switch ($Command) {
    "bump-patch" { Update-Version "patch" }
    "bump-minor" { Update-Version "minor" }
    "bump-major" { Update-Version "major" }
    "release-test" { Publish-Test }
    "release-prod" { Publish-Prod }
}
