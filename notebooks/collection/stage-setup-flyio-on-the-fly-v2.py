import marimo

__generated_with = "0.25.1"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _():
    import subprocess

    return (subprocess,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    <a href="https://colab.research.google.com/gist/vrtmrz/9402b101746e08e969b1a4f5f0deb465/setup-flyio-on-the-fly-v2.ipynb" target="_parent"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/></a>
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    - Initial version 7th Feb. 2024
    """)
    return


@app.cell
def _(subprocess):
    # Install prerequesties
    #! curl -L https://fly.io/install.sh | sh
    subprocess.call(['curl', '-L', 'https://fly.io/install.sh', '|', 'sh'])
    #! curl -fsSL https://deno.land/x/install/install.sh | sh
    subprocess.call(['curl', '-fsSL', 'https://deno.land/x/install/install.sh', '|', 'sh'])
    #! apt update && apt -y install jq
    subprocess.call(['apt', 'update', '&&', 'apt', '-y', 'install', 'jq'])
    import os
    os.environ['PATH'] = '/root/.fly/bin:/root/.deno/bin/:{os.environ["PATH"]}'
    #! git clone --recursive https://github.com/vrtmrz/obsidian-livesync
    subprocess.call(['git', 'clone', '--recursive', 'https://github.com/vrtmrz/obsidian-livesync'])
    return (os,)


@app.cell
def _(subprocess):
    # Login up sign up
    #! flyctl auth signup
    subprocess.call(['flyctl', 'auth', 'signup'])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Select a region and execute the block.
    """)
    return


@app.cell
def _(os, subprocess):
    # see https://fly.io/docs/reference/regions/
    region = 'nrt/Tokyo, Japan'  #@param ["jnb/Johannesburg, South Africa","bom/Mumbai, India","sin/Singapore, Singapore","syd/Sydney, Australia","nrt/Tokyo, Japan","ams/Amsterdam, Netherlands","fra/Frankfurt, Germany","lhr/London, United Kingdom","cdg/Paris, France","arn/Stockholm, Sweden","iad/Ashburn, Virginia (US)","ord/Chicago, Illinois (US)","dfw/Dallas, Texas (US)","lax/Los Angeles, California (US)","sjc/San Jose, California (US)","ewr/Secaucus, NJ (US)","yyz/Toronto, Canada","gru/Sao Paulo, Brazil"] {allow-input: true}
    os.environ['region'] = '{region.split("/")[0]}'
    os.chdir('obsidian-livesync/utils/flyio')
    #%env appame=
    #%env username=
    #%env password=
    #%env database=
    #%env passphrase=
    subprocess.call(['./deploy-server.sh', '|', 'tee', 'deploy-result.txt'])
    # automatic setup leave it  -->
    from IPython.display import HTML
    last_line = ''
    #! ./deploy-server.sh | tee deploy-result.txt
    with open('deploy-result.txt', 'r') as f:
        last_line = f.readlines()[-1]
    ## Show result button
        last_line = str.strip(last_line)
    if last_line.startswith('obsidian://'):
        result = HTML(f"""Copy your setup-URI with this button! -&gt; <button onclick="navigator.clipboard.writeText('{last_line}')">Copy setup uri</button><br>Importing passphrase is displayed one. <br>If you want to synchronise in live mode, please apply a preset after ensuring the imported configuration works.""")
    else:
        result = 'Failed to encrypt the setup URI'
    result
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    If you see the `Copy setup URI` button, Congratulations! Your CouchDB is ready to use! Please click the button. And open this on Obsidian.

    And, you should keep the output to your secret memo.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---

    If you want to delete this CouchDB instance, you can do it by executing next cell.
    If your fly.toml has been gone, access https://fly.io/dashboard and check the existing app.
    """)
    return


@app.cell
def _(subprocess):
    #! ./delete-server.sh
    subprocess.call(['./delete-server.sh'])
    return



@app.cell(hide_code=True)
def _():
    import marimo as _studio_mo
    studio_notes = _studio_mo.ui.text_area(label="Research notes", placeholder="Record parameters, observations and follow-up questions")
    _studio_mo.vstack([_studio_mo.md("### Research notebook"), studio_notes])
    return (studio_notes,)

if __name__ == "__main__":
    app.run()
