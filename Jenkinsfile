pipeline {
  agent { label 'docker' }
  stages {
    stage('Build') {
      steps {
        sh "docker build -t openstax/cnx-publishing:dev ."
      }
    }
    stage('Publish Dev Container') {
      when { branch 'master' }
      steps {
        // 'docker-registry' is defined in Jenkins under credentials
        withDockerRegistry([credentialsId: 'docker-registry', url: '']) {
          sh "docker push openstax/cnx-publishing:dev"
        }
      }
    }
    stage('Publish Release') {
      when { buildingTag() }
      environment {
        release = meta.version()
      }
      steps {
        withDockerRegistry([credentialsId: 'docker-registry', url: '']) {
          sh "docker tag openstax/cnx-publishing:dev openstax/cnx-publishing:${release}"
          sh "docker tag openstax/cnx-publishing:dev openstax/cnx-publishing:latest"
          sh "docker push openstax/cnx-publishing:${release}"
          sh "docker push openstax/cnx-publishing:latest"
        }
      }
    }
  }
}
