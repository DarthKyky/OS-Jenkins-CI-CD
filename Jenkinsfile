pipeline {
  agent any

  environment {
    IMAGE   = 'ubuntu-24.04'
    FLAVOR  = 'dev.medium'
    NETWORK = 'devnet'
    KEYPAIR = 'devteam-key'

    SSH_USER = 'ubuntu'
    SSH_KEY  = "${env.HOME}/.ssh/devteam"
  }

  stages {

    stage('Checkout') {
      steps {
        checkout scm
        sh 'ls -la'
      }
    }

    stage('Create ephemeral VM') {
      steps {
        withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
          sh '''#!/usr/bin/env bash
            set -euo pipefail

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
              "$VM_NAME"

            for i in {1..60}; do
              STATUS=$(openstack server show "$VM_NAME" -f value -c status || true)
              echo "status=$STATUS"
              if [[ "$STATUS" == "ACTIVE" ]]; then break; fi
              if [[ "$STATUS" == "ERROR" ]]; then
                echo "VM entered ERROR state"
                openstack server show "$VM_NAME"
                exit 1
              fi
              sleep 5
            done

            if [[ "$(openstack server show "$VM_NAME" -f value -c status)" != "ACTIVE" ]]; then
              echo "Timeout waiting for ACTIVE"
              openstack server show "$VM_NAME"
              exit 1
            fi
          '''
        }
      }
    }

    stage('Wait for IP on devnet') {
      steps {
        withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
          sh '''#!/usr/bin/env bash
            set -euo pipefail

            cp "$OPENRC" openrc.sh
            chmod 600 openrc.sh
            source ./openrc.sh

            VM_NAME=$(cat vm_name.txt)

            echo "Waiting for IP..."

            for i in {1..60}; do
              # robust-ish: works when "addresses" is dict; fallback when it's string
              RAW=$(openstack server show "$VM_NAME" -f json -c addresses)
              IP=$(echo "$RAW" | jq -r --arg net "$NETWORK" '
                (.addresses[$net][0] // .addresses) | tostring
              ')

              # if it's like "devnet=10.20.0.109"
              if [[ "$IP" == *"="* ]]; then
                IP="${IP##*=}"
              fi

              echo "ip=$IP"

              if [[ "$IP" != "null" && -n "$IP" ]]; then
                echo "$IP" > vm_ip.txt
                break
              fi
              sleep 5
            done

            if [[ ! -s vm_ip.txt ]]; then
              echo "Timeout waiting for IP"
              openstack server show "$VM_NAME"
              exit 1
            fi
          '''
        }
      }
    }

    stage('Run pytest on ephemeral VM') {
      steps {
        sh '''#!/usr/bin/env bash
          set -euo pipefail

          IP=$(cat vm_ip.txt)
          test -f "$SSH_KEY"
          chmod 600 "$SSH_KEY"

          echo "Waiting for SSH on $IP..."
          for i in {1..40}; do
            if ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
              -o ConnectTimeout=5 -i "$SSH_KEY" "$SSH_USER@$IP" 'echo SSH_OK' ; then
              break
            fi
            sleep 5
          done

          # ship repo to VM
          tar -czf repo.tgz .
          scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            -i "$SSH_KEY" repo.tgz "$SSH_USER@$IP:/tmp/repo.tgz"

          # run tests (pytest is in requirements.txt)
          ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            -i "$SSH_KEY" "$SSH_USER@$IP" '
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
              pytest -q --junitxml=reports/junit.xml
            '

          # pull junit report back to Jenkins
          rm -rf reports && mkdir -p reports
          scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            -i "$SSH_KEY" "$SSH_USER@$IP:~/work/reports/junit.xml" reports/junit.xml
        '''
      }
    }
  }

  post {
    always {
      junit 'reports/junit.xml'
      archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true

      withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
        sh '''#!/usr/bin/env bash
          set +e
          cp "$OPENRC" openrc.sh 2>/dev/null
          chmod 600 openrc.sh 2>/dev/null
          source ./openrc.sh 2>/dev/null

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
