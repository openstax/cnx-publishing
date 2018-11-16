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
    stage('Deploy to the Staging stack') {
      when { branch 'master' }
      steps {
        // Requires DOCKER_HOST be set in the Jenkins Configuration.
        // Using the environment variable enables this file to be
        // endpoint agnostic.
        sh "docker -H ${CNX_STAGING_DOCKER_HOST} service update --label-add 'git.commit-hash=${GIT_COMMIT}' --image openstax/cnx-archive:dev staging_publishing"
      }
    }
    stage('Run Functional Tests'){
      when { branch 'master' }
      steps {
          runCnxFunctionalTests(testingDomain: "${env.CNX_STAGING_DOCKER_HOST}")
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
