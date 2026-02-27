pipeline {
  agent any

  parameters {
    booleanParam(name: 'DEBUG_HOLD', defaultValue: false, description: 'Pause before cleanup to debug networking')
  }

  environment {
    IMAGE   = 'ubuntu-24.04'
    FLAVOR  = 'dev.medium'
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
        sh '''
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
          sh '''
            set -euxo pipefail
            cp "$OPENRC" openrc.sh
            chmod 600 openrc.sh
            source ./openrc.sh

            if ! openstack security group show "$CI_SG_NAME" >/dev/null 2>&1; then
              openstack security group create "$CI_SG_NAME" --description "CI: allow SSH+ICMP from ${CI_CIDR}"
            fi

            openstack security group rule create --ingress --ethertype IPv4 --protocol icmp --remote-ip "$CI_CIDR" "$CI_SG_NAME" || true
            openstack security group rule create --ingress --ethertype IPv4 --protocol tcp --dst-port 22 --remote-ip "$CI_CIDR" "$CI_SG_NAME" || true
          '''
        }
      }
    }

    stage('Create ephemeral VM') {
      steps {
        withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
          sh '''
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
              [[ "$STATUS" == "ACTIVE" ]] && break
              sleep 5
            done
          '''
        }
      }
    }

    stage('Wait for IP') {
      steps {
        withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
          sh '''
            set -euxo pipefail
            cp "$OPENRC" openrc.sh
            chmod 600 openrc.sh
            source ./openrc.sh

            VM_NAME=$(cat vm_name.txt)

            for i in {1..60}; do
              RAW=$(openstack server show "$VM_NAME" -f json -c addresses)
              IP=$(echo "$RAW" | jq -r --arg net "$NETWORK" '(.addresses[$net][0] // .addresses) | tostring')
              [[ "$IP" == *"="* ]] && IP="${IP##*=}"

              if [[ "$IP" != "null" && -n "$IP" ]]; then
                echo "$IP" > vm_ip.txt
                break
              fi
              sleep 5
            done
          '''
        }
      }
    }

    stage('Run pytest') {
      steps {
        sh '''
          set -euxo pipefail

          IP=$(cat vm_ip.txt)
          chmod 600 "$SSH_KEY"

          echo "Waiting for SSH..."
          for i in {1..120}; do
            if ssh $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP" 'echo SSH_OK'; then
              break
            fi
            sleep 5
          done

          # ✔️ КРИТИЧНА ПРАВКА
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
            pytest -q --junitxml=reports/junit.xml
          '

          scp $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP:~/work/reports/junit.xml" reports/junit.xml
        '''
      }
    }
  }

  post {
    always {
      junit testResults: 'reports/junit.xml', allowEmptyResults: true
      archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true

      script {
        if (params.DEBUG_HOLD) {
          input message: "DEBUG pause"
        }
      }

      withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
        sh '''
          set +e
          cp "$OPENRC" openrc.sh
          source ./openrc.sh

          VM_NAME=$(cat vm_name.txt 2>/dev/null)
          [[ -n "$VM_NAME" ]] && openstack server delete "$VM_NAME"
        '''
      }
    }
  }
}