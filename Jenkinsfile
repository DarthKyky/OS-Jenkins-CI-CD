def ensureCiSecurityGroup(script) {
  script.withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
    script.sh '''#!/usr/bin/env bash
      set -euo pipefail
      source "$OPENRC"

      if ! openstack security group show "$CI_SG_NAME" >/dev/null 2>&1; then
        openstack security group create "$CI_SG_NAME" --description "CI: allow SSH+ICMP from ${CI_CIDR}"
      fi

      ensure_rule() {
        local proto="$1"
        local remote="$2"
        local port="${3:-}"

        if [[ -n "$port" ]]; then
          if ! openstack security group rule list "$CI_SG_NAME" -f json | jq -e \
            --arg proto "$proto" --arg remote "$remote" --arg port "$port" \
            '.[] | select(."IP Protocol" == $proto and ."IP Range" == $remote and ."Port Range" == $port and .Direction == "ingress")' >/dev/null; then
            openstack security group rule create --ingress --ethertype IPv4 --protocol "$proto" --dst-port "$port" --remote-ip "$remote" "$CI_SG_NAME"
          fi
        else
          if ! openstack security group rule list "$CI_SG_NAME" -f json | jq -e \
            --arg proto "$proto" --arg remote "$remote" \
            '.[] | select(."IP Protocol" == $proto and ."IP Range" == $remote and .Direction == "ingress")' >/dev/null; then
            openstack security group rule create --ingress --ethertype IPv4 --protocol "$proto" --remote-ip "$remote" "$CI_SG_NAME"
          fi
        fi
      }

      ensure_rule icmp "$CI_CIDR"
      ensure_rule tcp "$CI_CIDR" "22:22"

      echo "=== SG $CI_SG_NAME rules ==="
      openstack security group rule list "$CI_SG_NAME"
    '''
  }
}

def createVm(script) {
  script.withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
    script.sh '''#!/usr/bin/env bash
      set -euo pipefail
      source "$OPENRC"

      VM_NAME="ci-ephemeral-${BUILD_NUMBER}"
      echo "$VM_NAME" > vm_name.txt

      openstack server create \
        --image "$IMAGE" \
        --flavor "$FLAVOR" \
        --network "$NETWORK" \
        --key-name "$KEYPAIR" \
        --security-group "$CI_SG_NAME" \
        --property ttl="60m" \
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
    '''
  }
}

def waitForIp(script) {
  script.withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
    script.sh '''#!/usr/bin/env bash
      set -euo pipefail
      source "$OPENRC"

      VM_NAME=$(cat vm_name.txt)

      echo "Waiting for IP..."
      for i in {1..60}; do
        RAW=$(openstack server show "$VM_NAME" -f json -c addresses)
        IP=$(echo "$RAW" | jq -r --arg net "$NETWORK" '(.addresses[$net][0] // .addresses) | tostring')

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
        openstack port list --server "$VM_NAME" -f table || true
        exit 1
      fi
    '''
  }
}

def debugOpenStackDiagnostics(script) {
  script.withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
    script.sh '''#!/usr/bin/env bash
      set -euo pipefail
      source "$OPENRC"

      VM_NAME=$(cat vm_name.txt)
      IP=$(cat vm_ip.txt)

      echo "=== Server info ==="
      openstack server show "$VM_NAME" -c status -c addresses -c OS-EXT-SRV-ATTR:host -c fault -f yaml || true

      echo "=== Ports ==="
      openstack port list --server "$VM_NAME" -f table || true

      PORT_ID=$(openstack port list --server "$VM_NAME" -f value -c ID | head -n1 || true)
      if [[ -n "$PORT_ID" ]]; then
        openstack port show "$PORT_ID" -f yaml || true
      fi

      echo "=== Console log ==="
      openstack console log show "$VM_NAME" | tail -n 120 || true

      echo "=== Ping ==="
      ping -c 2 "$IP" || true
    '''
  }
}

def waitForSsh(script) {
  script.sh '''#!/usr/bin/env bash
    set -euo pipefail

    IP=$(cat vm_ip.txt)
    test -f "$SSH_KEY"
    chmod 600 "$SSH_KEY"

    echo "Waiting for SSH on $IP..."
    for i in {1..120}; do
      echo "---- ssh try $i ----"
      ping -c 1 -W 1 "$IP" || true

      if ssh $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP" 'echo SSH_OK'; then
        echo "SSH is up"
        exit 0
      fi

      sleep 5
    done

    echo "SSH did not become available in time"
    exit 1
  '''
}

def waitForCloudInit(script) {
  script.sh '''#!/usr/bin/env bash
    set -euo pipefail

    IP=$(cat vm_ip.txt)
    chmod 600 "$SSH_KEY"

    echo "Waiting for cloud-init boot-finished..."
    for i in {1..120}; do
      if ssh $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP" 'test -f /var/lib/cloud/instance/boot-finished'; then
        echo "cloud-init finished"
        exit 0
      fi
      sleep 5
    done

    echo "Timeout waiting for cloud-init"
    ssh $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP" \
      'sudo cloud-init status --long || true; sudo journalctl -u cloud-init --no-pager -n 200 || true' \
      > reports/cloud-init-debug.log 2>&1 || true
    exit 1
  '''
}

def runPythonTests(script) {
  script.sh '''#!/usr/bin/env bash
    set -euo pipefail

    IP=$(cat vm_ip.txt)
    chmod 600 "$SSH_KEY"

    git archive --format=tar.gz -o repo.tgz HEAD
    scp $SSH_OPTS -i "$SSH_KEY" repo.tgz "$SSH_USER@$IP:/tmp/repo.tgz"

    ssh $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP" '
      set -euo pipefail

      sudo apt-get update
      sudo apt-get install -y python3-venv python3-pip

      mkdir -p ~/work && cd ~/work
      tar -xzf /tmp/repo.tgz
      cd Projects/Python
      mkdir -p reports

      {
        echo "=== system info ==="
        date
        uname -a
        echo

        echo "=== OS release ==="
        cat /etc/os-release || true
        echo

        echo "=== memory ==="
        free -h || true
        echo

        echo "=== disk ==="
        df -h || true
        echo

        echo "=== python ==="
        python3 --version || true
        pip3 --version || true
      } | tee reports/system-info.txt

      cp reports/system-info.txt reports/bootstrap.log

      python3 -m venv .venv
      . .venv/bin/activate
      pip install -U pip
      pip install -r requirements.txt

      export PYTHONPATH="$PWD"

      set +e
      pytest -q --rootdir=. --junitxml=reports/junit.xml 2>&1 | tee reports/pytest.log
      PYTEST_RC=$?
      echo "$PYTEST_RC" > reports/pytest_rc.txt
      set -e

      exit 0
    '
  '''
}

def runJavaTests(script) {
  script.sh '''#!/usr/bin/env bash
    set -euo pipefail

    IP=$(cat vm_ip.txt)
    chmod 600 "$SSH_KEY"

    git archive --format=tar.gz -o repo.tgz HEAD
    scp $SSH_OPTS -i "$SSH_KEY" repo.tgz "$SSH_USER@$IP:/tmp/repo.tgz"

    ssh $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP" '
      set -euo pipefail

      sudo apt-get update
      sudo apt-get install -y openjdk-21-jdk maven

      mkdir -p ~/work && cd ~/work
      tar -xzf /tmp/repo.tgz
      cd projects/java
      mkdir -p reports

      {
        echo "=== system info ==="
        date
        uname -a
        echo

        echo "=== OS release ==="
        cat /etc/os-release || true
        echo

        echo "=== memory ==="
        free -h || true
        echo

        echo "=== disk ==="
        df -h || true
        echo

        echo "=== java ==="
        java -version
        echo

        echo "=== maven ==="
        mvn -version
      } > reports/system-info.txt 2>&1

      cp reports/system-info.txt reports/bootstrap.log

      set +e
      mvn test > reports/maven-test.log 2>&1
      MVN_RC=$?
      echo "$MVN_RC" > reports/maven_rc.txt
      set -e

      if [[ -d target/surefire-reports ]]; then
        cp target/surefire-reports/*.xml reports/ 2>/dev/null || true
        cp target/surefire-reports/*.txt reports/ 2>/dev/null || true
      fi

      exit 0
    '
  '''
}

def collectPythonArtifacts(script) {
  script.sh '''#!/usr/bin/env bash
    set -euo pipefail

    IP=$(cat vm_ip.txt)
    chmod 600 "$SSH_KEY"
    mkdir -p reports

    scp -r $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP:~/work/projects/python/reports/." reports/ || true
  '''
}

def collectJavaArtifacts(script) {
  script.sh '''#!/usr/bin/env bash
    set -euo pipefail

    IP=$(cat vm_ip.txt)
    chmod 600 "$SSH_KEY"
    mkdir -p reports

    scp -r $SSH_OPTS -i "$SSH_KEY" "$SSH_USER@$IP:~/work/projects/java/reports/." reports/ || true
  '''
}

def cleanupVm(script) {
  script.withCredentials([file(credentialsId: 'openstack-openrc', variable: 'OPENRC')]) {
    script.sh '''#!/usr/bin/env bash
      set +e
      source "$OPENRC"

      if [[ -f vm_name.txt ]]; then
        VM_NAME=$(cat vm_name.txt)
        echo "Deleting ${VM_NAME}"
        openstack server delete "$VM_NAME" || true
      fi
    '''
  }
}

pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
  }

  parameters {
    choice(name: 'PROJECT_TYPE', choices: ['python', 'java'], description: 'Workload type for the ephemeral runner')
    booleanParam(name: 'DEBUG_VERBOSE', defaultValue: false, description: 'Run extra OpenStack diagnostics')
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
          set -euo pipefail
          rm -f vm_name.txt vm_ip.txt repo.tgz || true
          rm -rf reports || true
          mkdir -p reports
        '''
      }
    }

    stage('Ensure CI Security Group') {
      steps {
        script { ensureCiSecurityGroup(this) }
      }
    }

    stage('Create ephemeral VM') {
      steps {
        script { createVm(this) }
      }
    }

    stage('Wait for IP on devnet') {
      steps {
        script { waitForIp(this) }
      }
    }

    stage('Debug OpenStack diagnostics') {
      when {
        expression { return params.DEBUG_VERBOSE }
      }
      steps {
        echo 'DEBUG_VERBOSE enabled -> running OpenStack diagnostics'
        script { debugOpenStackDiagnostics(this) }
      }
    }

    stage('Wait for SSH') {
      steps {
        script { waitForSsh(this) }
      }
    }

    stage('Wait for cloud-init') {
      steps {
        script { waitForCloudInit(this) }
      }
    }

    stage('Run tests on ephemeral VM') {
      steps {
        script {
          switch (params.PROJECT_TYPE) {
            case 'python':
              runPythonTests(this)
              break
            case 'java':
              runJavaTests(this)
              break
            default:
              error("Unsupported PROJECT_TYPE: ${params.PROJECT_TYPE}")
          }
        }
      }
    }

    stage('Collect artifacts') {
      steps {
        script {
          switch (params.PROJECT_TYPE) {
            case 'python':
              collectPythonArtifacts(this)
              break
            case 'java':
              collectJavaArtifacts(this)
              break
            default:
              error("Unsupported PROJECT_TYPE: ${params.PROJECT_TYPE}")
          }
        }

        script {
          if (fileExists('reports/pytest_rc.txt')) {
            def rc = readFile('reports/pytest_rc.txt').trim()
            if (rc != '0') {
              currentBuild.result = 'UNSTABLE'
              echo "Pytest exit code=${rc} -> marking build UNSTABLE"
            }
          }

          if (fileExists('reports/maven_rc.txt')) {
            def rc = readFile('reports/maven_rc.txt').trim()
            if (rc != '0') {
              currentBuild.result = 'UNSTABLE'
              echo "Maven exit code=${rc} -> marking build UNSTABLE"
            }
          }
        }
      }
    }
  }

  post {
    always {
      sh '''#!/usr/bin/env bash
        set +e
        echo "=== Post summary ==="
        pwd
        echo "--- reports dir ---"
        ls -la reports 2>/dev/null || true
        echo "--- xml files ---"
        find . -maxdepth 4 -type f -name "*.xml" -print 2>/dev/null || true
      '''

      junit testResults: 'reports/**/*.xml', allowEmptyResults: true
      archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true

      script {
        if (params.DEBUG_HOLD) {
          input message: 'DEBUG_HOLD=true. VM stays alive. Click Continue to run cleanup.'
        }
      }

      script { cleanupVm(this) }
    }
  }
}
