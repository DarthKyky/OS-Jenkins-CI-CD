pipeline {
  agent any

  parameters {
    booleanParam(name: 'DEBUG_HOLD', defaultValue: false, description: 'Pause before cleanup to debug networking')
  }

  environment {
    IMAGE   = 'ubuntu-24.04'
    FLAVOR  = 'dev.large'
    NETWORK = 'devnet'
    KEYPAIR = 'devteam-key'

    SSH_USER = 'ubuntu'
    SSH_KEY  = '/var/lib/jenkins/.ssh/devteam'


    SSH_OPTS = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 -o IdentitiesOnly=yes'
    CI_SG_NAME = 'ci-ssh'
    CI_CIDR    = '10.20.0.0/24'
  }

  stages {

    stage('Init') {
      steps {
        sh '''#!/usr/bin/env bash
          set -euxo pipefail
          rm -f vm_name.txt vm_ip.txt openrc.sh repo.tgz || true
          rm -rf reports || true
          mkdir -p reports
        '''
      }
    }

    stage('Checkout') {
      steps {
        checkout scm
        sh 'ls -la'
      }
    }

    stage('Ensure CI Security Group') {
      steps {
        withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
          sh '''#!/usr/bin/env bash
            set -euxo pipefail
            cp "$OPENRC" openrc.sh
            chmod 600 openrc.sh
            source ./openrc.sh

            if ! openstack security group show "$CI_SG_NAME" >/dev/null 2>&1; then
              openstack security group create "$CI_SG_NAME" --description "CI: allow SSH+ICMP from ${CI_CIDR}"
            fi

            openstack security group rule create --ingress --ethertype IPv4 --protocol icmp --remote-ip "$CI_CIDR" "$CI_SG_NAME" || true
            openstack security group rule create --ingress --ethertype IPv4 --protocol tcp --dst-port 22 --remote-ip "$CI_CIDR" "$CI_SG_NAME" || true

            echo "=== SG $CI_SG_NAME rules ==="
            openstack security group rule list "$CI_SG_NAME"
          '''
        }
      }
    }

    stage('Create ephemeral VM') {
      steps {
        withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
          sh '''#!/usr/bin/env bash
            set -euxo pipefail

            cp "$OPENRC" openrc.sh
            chmod 600 openrc.sh
            source ./openrc.sh

            VM_NAME="ci-ephemeral-${BUILD_NUMBER}"
            echo "$VM_NAME" > vm_name.txt

            openstack server create \
              --image "$IMAGE" \
              --flavor "$FLAVOR" \
              --network "$NETWORK" \
              --key-name "$KEYPAIR" \
              --security-group "$CI_SG_NAME" \
              "$VM_NAME"

            for i in {1..60}; do
              STATUS=$(openstack server show "$VM_NAME" -f value -c status || true)
              echo "status=$STATUS"
              if [[ "$STATUS" == "ACTIVE" ]]; then break; fi
              if [[ "$STATUS" == "ERROR" ]]; then
                echo "VM entered ERROR state"
                openstack server show "$VM_NAME" -f yaml || true
                exit 1
              fi
              sleep 5
            done

            if [[ "$(openstack server show "$VM_NAME" -f value -c status)" != "ACTIVE" ]]; then
              echo "Timeout waiting for ACTIVE"
              openstack server show "$VM_NAME" -f yaml || true
              exit 1
            fi

            echo "=== Ports for $VM_NAME (table) ==="
            openstack port list --server "$VM_NAME" -f table || true
          '''
        }
      }
    }

    stage('Wait for IP on devnet') {
      steps {
        withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
          sh '''#!/usr/bin/env bash
            set -euxo pipefail

            cp "$OPENRC" openrc.sh
            chmod 600 openrc.sh
            source ./openrc.sh

            VM_NAME=$(cat vm_name.txt)

            echo "Waiting for IP..."
            for i in {1..60}; do
              RAW=$(openstack server show "$VM_NAME" -f json -c addresses)
              IP=$(echo "$RAW" | jq -r --arg net "$NETWORK" '(.addresses[$net][0] // .addresses) | tostring')

              # інколи OpenStack показує ip_address='x.x.x.x'
              if [[ "$IP" == *"="* ]]; then IP="${IP##*=}"; fi

              echo "ip=$IP"
              if [[ "$IP" != "null" && -n "$IP" ]]; then
                echo "$IP" > vm_ip.txt
                break
              fi
              sleep 5
            done

            if [[ ! -s vm_ip.txt ]]; then
              echo "Timeout waiting for IP"
              openstack server show "$VM_NAME" -f yaml || true
              echo "=== Ports debug ==="
              openstack port list --server "$VM_NAME" -f table || true
              exit 1
            fi
          '''
        }
      }
    }

    stage('Debug Neutron port + console log') {
      steps {
        withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
          sh '''#!/usr/bin/env bash
            set -euxo pipefail

            cp "$OPENRC" openrc.sh
            chmod 600 openrc.sh
            source ./openrc.sh

            VM_NAME=$(cat vm_name.txt)
            IP=$(cat vm_ip.txt)

            echo "=== Server show (key fields) ==="
            openstack server show "$VM_NAME" -c status -c addresses -c OS-EXT-SRV-ATTR:host -c fault -f yaml || true

            echo "=== Port list for server (table) ==="
            openstack port list --server "$VM_NAME" -f table || true

            PORT_ID=$(openstack port list --server "$VM_NAME" -f value -c ID | head -n1 || true)
            echo "PORT_ID=$PORT_ID"

            if [[ -n "$PORT_ID" ]]; then
              echo "=== Port show (yaml) ==="
              openstack port show "$PORT_ID" -f yaml || true
            fi

            echo "=== Console log (last 120 lines) ==="
            openstack console log show "$VM_NAME" | tail -n 120 || true

            echo "=== From Jenkins (service user context may differ): ping $IP ==="
            ping -c 2 "$IP" || true
          '''
        }
      }
    }

    stage('Run pytest on ephemeral VM') {
      steps {
        sh '''#!/usr/bin/env bash
          set -euxo pipefail

          IP=$(cat vm_ip.txt)
          echo "Target IP: $IP"

          echo "=== Local (Jenkins VM) ==="
          whoami || true
          ip a || true
          ip route || true

          test -f "$SSH_KEY"
          chmod 600 "$SSH_KEY"
          echo "Waiting for SSH on $IP..."
          for i in {1..120}; do
            echo "---- try $i ----"
            ip neigh show | grep -E "$IP|FAILED|INCOMPLETE" || true
            ping -c 1 -W 1 "$IP" || true

            if ssh $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP" 'echo SSH_OK' ; then
              echo "SSH is up"
              break
            fi
            sleep 5
          done

          # hard fail if still not reachable
          ssh $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP" 'echo SSH_OK_FINAL'

          git archive --format=tar.gz -o repo.tgz HEAD

          scp $SSH_OPTS -i "$SSH_KEY" repo.tgz "$SSH_USER@$IP:/tmp/repo.tgz"

          ssh $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP" '
              set -euxo pipefail
              sudo apt-get update
              sudo apt-get install -y python3-venv python3-pip

              mkdir -p ~/work && cd ~/work
              tar -xzf /tmp/repo.tgz

              python3 -m venv .venv
              . .venv/bin/activate
              pip install -U pip
              pip install -r requirements.txt
              mkdir -p reports
              export PYTHONPATH="$PWD"

              set +e
              pytest -q --rootdir=. --junitxml=reports/junit.xml
              PYTEST_RC=$?
              echo "$PYTEST_RC" > reports/pytest_rc.txt
              set -e

              # do not fail the SSH session due to test failures; Jenkins will mark UNSTABLE based on pytest_rc.txt
              exit 0
            '

          scp $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP:~/work/reports/junit.xml" reports/junit.xml
          scp $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP:~/work/reports/pytest_rc.txt" reports/pytest_rc.txt
        '''
      script {
  // Mark build UNSTABLE if pytest had failures (but keep pipeline running to publish reports/cleanup)
  if (fileExists('reports/pytest_rc.txt')) {
    def rc = readFile('reports/pytest_rc.txt').trim()
    if (rc != '0') {
      currentBuild.result = 'UNSTABLE'
      echo "Pytest exit code=${rc} → marking build UNSTABLE"
    }
  } else {
    echo "No reports/pytest_rc.txt found (pytest may not have run)"
  }
}
      }
    }
  }

  post {
    always {
      sh '''#!/usr/bin/env bash
        set +e
        echo "=== Post debug (workspace) ==="
        pwd
        ls -la
        echo "--- reports dir ---"
        ls -la reports 2>/dev/null || true
        echo "--- find junit.xml ---"
        find . -maxdepth 4 -type f -name "junit.xml" -print 2>/dev/null || true
      '''

      junit testResults: 'reports/junit.xml', allowEmptyResults: true
      archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true

      // script {
      //   if (!env.GIT_COMMIT) {
      //     echo "GIT_COMMIT is not set. Skipping GitHub comment."
      //     return
      //   }
      //   if (!fileExists('reports/junit.xml')) {
      //     echo "reports/junit.xml not found. Skipping GitHub comment."
      //     return
      //   }

      //   def xmlText = readFile('reports/junit.xml')
      //   def root = new XmlSlurper(false, false).parseText(xmlText)

      //   int totalTests = 0
      //   int totalFailures = 0
      //   def failedDetails = []

      //   // Уникаємо root.testsuite / root.testcase — використовуємо ['testsuite']
      //   def suites = (root.name() == 'testsuite') ? [root] : root['testsuite']

      //   suites.each { ts ->
      //     // attributes() замість ts.@tests / ts.@failures
      //     def tsAttrs = ts.attributes()
      //     totalTests += ((tsAttrs['tests'] ?: "0") as String).isInteger() ? (tsAttrs['tests'] as int) : 0
      //     totalFailures += ((tsAttrs['failures'] ?: "0") as String).isInteger() ? (tsAttrs['failures'] as int) : 0

      //     // Уникаємо ts.testcase — використовуємо ['testcase']
      //     ts['testcase'].each { tc ->
      //       // Уникаємо tc.failure — використовуємо ['failure']
      //       def failures = tc['failure']
      //       if (failures != null && failures.size() > 0) {
      //         def tcAttrs = tc.attributes()
      //         def className = (tcAttrs['classname'] ?: "").toString()
      //         def testName  = (tcAttrs['name'] ?: "").toString()

      //         def failureText = failures[0].text()
      //         def shortened = failureText.readLines().take(20).join("\n")

      //         // Без """...""" і без ``` щоб не ламалося при копіпасті
      //         def block = "**" + className + " :: " + testName + "**\n\n"
      //         block += "----\n" + shortened + "\n----\n"
      //         failedDetails << block
      //       }
      //     }
      //   }

      //   def statusEmoji = (currentBuild.currentResult == 'UNSTABLE') ? "🟡" : "🟢"
      //   def summary = "## " + statusEmoji + " CI Test Report\n\n"
      //   summary += "- Total tests: **" + totalTests + "**\n"
      //   summary += "- Failures: **" + totalFailures + "**\n"
      //   summary += "- Jenkins result: **" + currentBuild.currentResult + "**\n\n"

      //   if (failedDetails && failedDetails.size() > 0) {
      //     summary += "### Failed Tests\n"
      //     failedDetails.each { summary += it + "\n" }
      //   } else {
      //     summary += "###All tests passed\n"
      //   }

      //   summary += "\n View full Jenkins build: " + env.BUILD_URL + "\n"

      //   withCredentials([string(credentialsId: 'github-pat', variable: 'GITHUB_TOKEN')]) {
      //     def payload = groovy.json.JsonOutput.toJson([body: summary])
      //     sh """
      //       curl -s -X POST \
      //         -H "Authorization: token \$GITHUB_TOKEN" \
      //         -H "Accept: application/vnd.github+json" \
      //         https://api.github.com/repos/DarthKyky/OS-Jenkins-CI-CD/commits/${env.GIT_COMMIT}/comments \
      //         -d '${payload}'
      //     """
      //   }
      // }

      script {
        if (params.DEBUG_HOLD) {
          input message: "DEBUG_HOLD=true. VM лишається живою. Натисни Continue щоб зробити cleanup."
        }
      }

      withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
        sh '''#!/usr/bin/env bash
          set +e
          cp "$OPENRC" openrc.sh 2>/dev/null
          chmod 600 openrc.sh 2>/dev/null
          . ./openrc.sh 2>/dev/null

          if [[ -f vm_name.txt ]]; then
            VM_NAME=$(cat vm_name.txt)
            echo "Deleting $VM_NAME"
            openstack server delete "$VM_NAME" || true
          fi
        '''
      }
    }
  }
}